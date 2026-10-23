"""Shared owner authorization, atomic writes, idempotent creation and manual approval gates."""

import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from app.db.base import utc_now
from app.domain.approvals import ApprovalStore
from app.domain.authorization import OwnerAuthorization
from app.domain.core import data_values, resource_id, text_value, to_record
from app.domain.errors import (
    CalendarConflictError,
    ConfirmationRequired,
    DuplicateRequestError,
    StaleWriteError,
    StorageError,
    ValidationError,
)
from app.domain.time import as_utc


class CoreService:
    repository_type = None
    data_type = None
    record_type = None
    kind = ""

    def __init__(
        self, sessions, authorization: OwnerAuthorization, *, approvals: ApprovalStore | None = None
    ):
        self.sessions, self.authorization = sessions, authorization
        self.approvals = approvals if approvals is not None else ApprovalStore()

    def authorize(self, actor_id: int):
        self.authorization.require_owner(actor_id)
        return str(actor_id)

    def validate_data(self, data):
        if type(data) is not self.data_type:
            raise ValidationError("Dữ liệu đầu vào không đúng loại.")
        return self.data_type(**data_values(data))

    @asynccontextmanager
    async def transaction(self, *, write=False):
        try:
            async with self.sessions.begin() as session:
                if write:
                    await session.connection(execution_options={"nova_sqlite_immediate": True})
                yield session
        except StaleDataError:
            raise StaleWriteError() from None
        except SQLAlchemyError:
            raise StorageError() from None

    def repository(self, session, owner):
        return self.repository_type(session, owner)

    async def get(self, actor_id: int, record_id: str):
        owner = self.authorize(actor_id)
        resource_id(record_id)
        async with self.transaction() as session:
            return to_record(self.record_type, await self.repository(session, owner).get(record_id))

    async def validate_references(self, session, owner, data):
        pass

    async def gate(self, repository, owner, data, before, record_id, approval_token):
        return None

    def creation_values(self, data):
        return data_values(data)

    def check_new_status(self, data):
        if data.status in {"cancelled", "archived"}:
            raise ValidationError("Không tạo bản ghi mới ở trạng thái hủy hoặc lưu trữ.")

    def require_approval(
        self, owner, operation, record_id, data, before, *, token, reason, conflicts=()
    ):
        payload = {
            "kind": self.kind,
            "operation": operation,
            "id": record_id,
            "data": asdict(data),
            "before": asdict(before) if before else None,
            "conflicts": [asdict(row) for row in conflicts],
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=lambda value: value.isoformat()).encode()
        ).hexdigest()
        if token is None:
            request = self.approvals.issue(
                owner, fingerprint, reason=reason, before=before, after=data, conflicts=conflicts
            )
            raise (CalendarConflictError if conflicts else ConfirmationRequired)(request)
        self.approvals.check(token, owner, fingerprint)
        return token

    async def create(
        self, actor_id: int, data, *, request_id: str, approval_token: str | None = None
    ):
        owner = self.authorize(actor_id)
        data = self.validate_data(data)
        key = text_value(request_id, 128)
        self.check_new_status(data)
        record_id = str(uuid5(NAMESPACE_URL, f"nova:{self.kind}:{owner}:{key}"))
        used_token = None
        async with self.transaction(write=True) as session:
            repository = self.repository(session, owner)
            existing = await repository.get(record_id, required=False)
            if existing is not None:
                if any(getattr(existing, key) != value for key, value in data_values(data).items()):
                    raise DuplicateRequestError()
                return to_record(self.record_type, existing)
            await self.validate_references(session, owner, data)
            used_token = await self.gate(repository, owner, data, None, record_id, approval_token)
            result = to_record(
                self.record_type, await repository.add(record_id, self.creation_values(data))
            )
        self.approvals.consume(used_token)
        return result

    def check_expected(self, before, expected):
        if hasattr(before, "version"):
            if type(expected) is not int or expected < 1:
                raise ValidationError("Cần version nguyên dương của bản ghi đang sửa.")
            if before.version != expected:
                raise StaleWriteError()
        else:
            if not isinstance(expected, datetime):
                raise ValidationError("Cần updated_at của project đang sửa.")
            if before.updated_at != as_utc(expected):
                raise StaleWriteError()

    async def update(
        self, actor_id: int, record_id: str, data, *, expected, approval_token: str | None = None
    ):
        owner = self.authorize(actor_id)
        resource_id(record_id)
        data = self.validate_data(data)
        used_token = None
        async with self.transaction(write=True) as session:
            repository = self.repository(session, owner)
            before = to_record(self.record_type, await repository.get(record_id))
            self.check_expected(before, expected)
            await self.validate_references(session, owner, data)
            used_token = await self.gate(repository, owner, data, before, record_id, approval_token)
            values = self.update_values(data, before)
            values["updated_at"] = max(utc_now(), before.updated_at + timedelta(microseconds=1))
            result = to_record(
                self.record_type, await repository.update(record_id, values, expected)
            )
        self.approvals.consume(used_token)
        return result

    def update_values(self, data, before):
        return data_values(data)
