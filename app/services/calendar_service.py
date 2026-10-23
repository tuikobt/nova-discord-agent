from dataclasses import fields, replace
from datetime import date, datetime, time, timedelta

from app.db.repositories.calendar_repository import CalendarRepository
from app.db.repositories.task_repository import TaskRepository
from app.domain.core import EventData, EventRecord, Page, enum_value, pagination, to_record
from app.domain.enums import EventStatus
from app.domain.errors import ValidationError
from app.domain.time import DEFAULT_TIMEZONE, as_utc, zone
from app.services.core_service import CoreService


def local_window(day: date, days: int, timezone: str):
    tz = zone(timezone)
    try:
        end = day + timedelta(days=days)
    except OverflowError:
        raise ValidationError("Khoảng ngày nằm ngoài phạm vi hỗ trợ.") from None
    return datetime.combine(day, time.min, tzinfo=tz), datetime.combine(end, time.min, tzinfo=tz)


class CalendarService(CoreService):
    repository_type, data_type, record_type, kind = (
        CalendarRepository,
        EventData,
        EventRecord,
        "event",
    )

    async def validate_references(self, session, owner, data):
        if data.task_id is not None:
            await TaskRepository(session, owner).get(data.task_id)

    async def list(self, actor_id: int, starts_at, ends_at, *, status=None, page=0, page_size=10):
        owner = self.authorize(actor_id)
        pagination(page, page_size)
        starts_at, ends_at = as_utc(starts_at), as_utc(ends_at)
        if ends_at <= starts_at:
            raise ValidationError("Khoảng thời gian không hợp lệ.")
        status = enum_value(EventStatus, status) if status is not None else None
        async with self.transaction() as session:
            rows, total = await self.repository(session, owner).list(
                starts_at, ends_at, status=status, page=page, page_size=page_size
            )
            return Page(tuple(to_record(EventRecord, row) for row in rows), total, page, page_size)

    async def list_day(
        self,
        actor_id: int,
        day: date,
        *,
        timezone=DEFAULT_TIMEZONE,
        status=None,
        page=0,
        page_size=10,
    ):
        self.authorize(actor_id)
        if type(day) is not date:
            raise ValidationError("Cần ngày cụ thể gồm năm, tháng và ngày.")
        return await self.list(
            actor_id,
            *local_window(day, 1, timezone),
            status=status,
            page=page,
            page_size=page_size,
        )

    async def list_week(
        self,
        actor_id: int,
        day: date,
        *,
        timezone=DEFAULT_TIMEZONE,
        status=None,
        page=0,
        page_size=10,
    ):
        self.authorize(actor_id)
        if type(day) is not date:
            raise ValidationError("Cần ngày cụ thể gồm năm, tháng và ngày.")
        monday = day - timedelta(days=day.weekday())
        return await self.list(
            actor_id,
            *local_window(monday, 7, timezone),
            status=status,
            page=page,
            page_size=page_size,
        )

    async def cancel(self, actor_id: int, event_id: str, *, expected, approval_token=None):
        before = await self.get(actor_id, event_id)
        data = EventData(**{field.name: getattr(before, field.name) for field in fields(EventData)})
        return await self.update(
            actor_id,
            event_id,
            replace(data, status="cancelled"),
            expected=expected,
            approval_token=approval_token,
        )

    async def gate(self, repository, owner, data, before, record_id, approval_token):
        conflicts = ()
        if data.status == "confirmed":
            conflicts = tuple(
                to_record(EventRecord, row)
                for row in await repository.conflicts(
                    data.starts_at, data.ends_at, exclude_id=before.id if before else None
                )
            )
        protected = before is not None and (
            before.status == "confirmed"
            or (data.status == "cancelled" and before.status != "cancelled")
        )
        if conflicts or protected or approval_token is not None:
            return self.require_approval(
                owner,
                "update" if before else "create",
                record_id,
                data,
                before,
                token=approval_token,
                reason="overlap" if conflicts else "change_event",
                conflicts=conflicts,
            )
        return None
