"""Connection consent, versioned scope checks and explicit provider diagnostics."""

import asyncio
from uuid import uuid4

from sqlalchemy import func, select

from app.db.base import utc_now
from app.db.models import AuditLog, IntegrationConnection, User
from app.domain.connections import ConnectionData, resource_key
from app.domain.core import resource_id
from app.domain.errors import NotFoundError, StaleWriteError, ValidationError
from app.integrations.config import CREDENTIAL_REFS, ConnectionCredentials
from app.integrations.errors import MESSAGES
from app.integrations.protocol import ProbeResult
from app.security import SecretFilter
from app.services.core_service import CoreService

PROBE_ERRORS = set(MESSAGES) - {"missing_credential"}


class ConnectionService(CoreService):
    def __init__(self, sessions, authorization, *, credentials=None, clock=utc_now):
        super().__init__(sessions, authorization)
        self.credentials = credentials or ConnectionCredentials()
        self.secrets = SecretFilter(self.credentials.registered())
        self.clock, self.probes, self.on_change = clock, {}, None

    async def row(self, session, owner, key):
        resource_id(key)
        row = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.owner_id == owner, IntegrationConnection.id == key
            )
        )
        if row is None:
            raise NotFoundError()
        return row

    def record(self, row):
        return dict(
            id=row.id,
            provider=row.provider,
            label=row.label,
            resources=list(row.resources_json),
            status=row.status,
            version=row.version,
            requested_permissions=list(row.requested_permissions_json),
            verified_permissions=row.granted_permissions_json,
            last_checked_at=row.last_checked_at.isoformat() if row.last_checked_at else None,
            last_error_code=row.last_error_code,
        )

    async def get(self, actor, key):
        owner = self.authorize(actor)
        async with self.transaction() as session:
            return self.record(await self.row(session, owner, key))

    async def list(self, actor, page=0):
        owner = self.authorize(actor)
        if type(page) is not int or page < 0:
            raise ValidationError("Trang kết nối không hợp lệ.")
        async with self.transaction() as session:
            scope = IntegrationConnection.owner_id == owner
            total = await session.scalar(
                select(func.count()).select_from(IntegrationConnection).where(scope)
            )
            rows = await session.scalars(
                select(IntegrationConnection)
                .where(scope)
                .order_by(IntegrationConnection.created_at, IntegrationConnection.id)
                .offset(page * 5)
                .limit(5)
            )
            return dict(items=[self.record(row) for row in rows], total=total, page=page)

    async def plan(self, session, owner, kind, args):
        before = None
        if args.get("connection_id"):
            row = await self.row(session, owner, args["connection_id"])
            if row.version != args["expected_version"]:
                raise StaleWriteError()
            before = self.record(row)
        elif kind != "configure_connection" or args["expected_version"] != 0:
            raise ValidationError("Kết nối mới cần version bằng 0.")
        if kind == "disconnect_connection":
            after = {**before, "status": "disconnected"}
            # The configuration remains so an owner may deliberately reconnect later.
            after.pop("version")
            after.pop("id")
        elif kind == "configure_connection":
            data = ConnectionData(args["provider"], args["label"], args["resources"]).normalized(
                self.secrets
            )
            if before and data["provider"] != before["provider"]:
                raise ValidationError(
                    "Không đổi nhà cung cấp của kết nối đã có; hãy tạo kết nối khác."
                )
            duplicate = await session.scalar(
                select(IntegrationConnection.id).where(
                    IntegrationConnection.owner_id == owner,
                    IntegrationConnection.provider == data["provider"],
                    IntegrationConnection.label == data["label"],
                    IntegrationConnection.id != (args.get("connection_id") or ""),
                )
            )
            if duplicate:
                raise ValidationError("Tên kết nối đã tồn tại; chọn mục đã có để sửa phạm vi.")
            after = dict(
                **data,
                status="configured",
                requested_permissions=["read"],
                verified_permissions=None,
                last_checked_at=None,
                last_error_code=None,
            )
        else:
            raise ValidationError("Hành động kết nối không được cấp quyền.")
        user = await session.get(User, owner)
        return dict(
            connection_kind=kind,
            args=args,
            timezone=user.timezone,
            changes=[
                dict(entity="connection", id=args.get("connection_id"), before=before, after=after)
            ],
            references=[],
            conflicts=[],
            reminders=[],
        )

    async def apply(self, session, owner, plan):
        change = plan["changes"][0]
        before, after = change["before"], change["after"]
        key = change["id"] or str(uuid4())
        row = (
            await self.row(session, owner, key)
            if before
            else IntegrationConnection(
                id=key,
                owner_id=owner,
                provider=after["provider"],
                credential_ref=CREDENTIAL_REFS[after["provider"]],
                created_at=self.clock(),
                version=0,
            )
        )
        row.label, row.resources_json = after["label"], list(after["resources"])
        row.requested_permissions_json = ["read"]
        row.granted_permissions_json = None
        row.status, row.last_error_code = after["status"], None
        row.last_checked_at = None
        row.updated_at, row.version = self.clock(), row.version + 1
        session.add(row)
        await session.flush()
        if self.on_change:
            self.on_change(int(owner))
        return [key]

    async def authorize_resource(
        self, actor, key, resource, *, expected_version, permission="read"
    ):
        owner = self.authorize(actor)
        if permission != "read":
            raise ValidationError("Kết nối chỉ cho phép đọc trong phạm vi đã duyệt.")
        async with self.transaction() as session:
            row = await self.row(session, owner, key)
            if row.status == "disconnected":
                raise ValidationError("Kết nối đã ngắt; không được đọc tài nguyên.")
            if type(expected_version) is not int or row.version != expected_version:
                raise StaleWriteError()
            target = resource_key(row.provider, resource)
            if target not in row.resources_json or row.requested_permissions_json != ["read"]:
                raise ValidationError("Tài nguyên nằm ngoài phạm vi bạn đã duyệt.")
            # This is an authorization receipt, never a provider response or credential.
            return dict(
                connection_id=row.id,
                provider=row.provider,
                resource=target,
                version=row.version,
                permission="read",
            )

    async def check(self, actor, key):
        owner = self.authorize(actor)
        async with self.transaction() as session:
            row = await self.row(session, owner, key)
            snapshot = self.record(row)
        if snapshot["status"] == "disconnected":
            return dict(status="disconnected", network_attempted=False)
        provider = snapshot["provider"]
        if not self.credentials.resolve(provider):
            return dict(status="missing_credential", network_attempted=False)
        probe = self.probes.get(provider)
        if probe is None:
            return dict(status="adapter_pending", network_attempted=False)

        async def authorize(resource):
            return await self.authorize_resource(
                actor, key, resource, expected_version=snapshot["version"]
            )

        try:
            async with asyncio.timeout(10):
                result = await probe.check(
                    token=self.credentials.resolve(provider),
                    resources=tuple(snapshot["resources"]),
                    authorize=authorize,
                )
            if (
                not isinstance(result, ProbeResult)
                or type(result.ok) is not bool
                or result.ok
                and result.error_code is not None
            ):
                result = ProbeResult(False, "unknown_error")
            elif not result.ok and result.error_code not in PROBE_ERRORS:
                result = ProbeResult(False, "unknown_error")
        except TimeoutError:
            result = ProbeResult(False, "timeout")
        except Exception:
            result = ProbeResult(False, "unknown_error")
        async with self.transaction(write=True) as session:
            row = await self.row(session, owner, key)
            if row.version != snapshot["version"] or row.status == "disconnected":
                raise StaleWriteError()
            row.status = "verified" if result.ok else "configured"
            row.last_error_code = None if result.ok else result.error_code
            row.granted_permissions_json = ["read"] if result.ok else None
            row.last_checked_at = row.updated_at = self.clock()
            row.version += 1
            session.add(
                AuditLog(
                    owner_id=owner,
                    actor="owner",
                    action="connection.check",
                    entity_type="integration_connection",
                    entity_id=row.id,
                    result="success" if result.ok else "error",
                    safe_metadata_json={"provider": provider, "code": row.last_error_code},
                )
            )
            if self.on_change:
                self.on_change(actor)
        return dict(status="verified" if result.ok else result.error_code, network_attempted=True)
