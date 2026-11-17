"""Durable proposals. Only an authenticated Discord callback can execute them.

The mutation, audit and receipt share one SQLite writer transaction. Existing P3
services retain their manual gates; this executor reuses their validators/repos.
"""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.agent.serialization import plain
from app.agent.tool_registry import WRITES, timestamp, validate
from app.db.base import utc_now
from app.db.models import (
    AuditLog,
    CalendarEvent,
    PendingAction,
    Reminder,
    ReminderDelivery,
    Task,
    User,
)
from app.db.repositories.calendar_repository import CalendarRepository
from app.db.repositories.task_repository import TaskRepository
from app.domain.core import EventData, TaskData, to_record
from app.domain.errors import (
    ApprovalInvalidError,
    DuplicateRequestError,
    NotFoundError,
    StaleWriteError,
    ValidationError,
)
from app.domain.reminder_delivery import ReminderRecord
from app.domain.reminders import RecurrenceRule, ReminderData, discord_id
from app.domain.time import zone
from app.services.core_service import CoreService


class PendingActionService(CoreService):
    def __init__(self, sessions, authorization, core, *, clock=utc_now):
        super().__init__(sessions, authorization)
        self.core, self.clock = core, clock

    async def get_row(self, session, owner, key):
        row = await session.scalar(
            select(PendingAction).where(PendingAction.id == key, PendingAction.owner_id == owner)
        )
        if row is None:
            raise NotFoundError()
        return row

    async def existing(self, actor, turn):
        owner = self.authorize(actor)
        async with self.transaction() as session:
            row = await session.scalar(
                select(PendingAction).where(
                    PendingAction.owner_id == owner, PendingAction.idempotency_key == str(turn)
                )
            )
            return self.result(row) if row else None

    def result(self, row):
        return dict(
            id=row.id,
            status=row.status,
            action=row.action_type,
            preview=row.payload_json,
            expires_at=row.expires_at.isoformat(),
            receipt=row.result_json,
            channel_id=row.channel_id,
            message_id=row.message_id,
        )

    async def get(self, actor, key):
        owner = self.authorize(actor)
        async with self.transaction() as session:
            return self.result(await self.get_row(session, owner, key))

    async def plan(self, session, owner, kind, args):
        """Rebuilt at approval; any changed record or new conflict invalidates preview."""
        args = validate(kind, args)
        user = await session.get(User, owner)
        tz = user.timezone
        changes, references, conflicts, reminders = [], [], [], []
        if kind == "create_task":
            data = TaskData(**{**args, "due_at": timestamp(args["due_at"])})
            await self.core.tasks.validate_references(session, owner, data)
            changes.append(dict(entity="task", id=None, before=None, after=plain(data)))
        elif kind == "create_calendar_event":
            data = EventData(
                **{
                    **args,
                    "starts_at": timestamp(args["starts_at"]),
                    "ends_at": timestamp(args["ends_at"]),
                }
            )
            await self.core.calendar.validate_references(session, owner, data)
            changes.append(dict(entity="event", id=None, before=None, after=plain(data)))
        elif kind == "create_reminder":
            fire = timestamp(args["first_fire_at"])
            local = fire.astimezone(zone(tz))
            recurrence = args["recurrence_type"]
            rule = (
                RecurrenceRule(
                    time=local.strftime("%H:%M"),
                    timezone=tz,
                    weekday=local.weekday() if recurrence == "weekly" else None,
                )
                if recurrence != "none"
                else None
            )
            data = ReminderData(
                title=args["title"],
                next_fire_at=fire,
                recurrence_type=recurrence,
                recurrence=rule,
                task_id=args["task_id"],
                event_id=args["event_id"],
            )
            data.validate_create(now=self.clock())
            await self.core.reminders.references(session, owner, data)
            changes.append(
                dict(entity="reminder", id=None, before=None, after=plain(data.to_storage()))
            )
        elif kind in {"complete_task", "propose_bulk_task_update"}:
            ids = [args["task_id"]] if kind == "complete_task" else args["task_ids"]
            if len(set(ids)) != len(ids):
                raise ValidationError("Không lặp ID task trong cùng đề xuất.")
            for key in ids:
                row = await TaskRepository(session, owner).get(key)
                before = to_record(TaskData, row)
                updates = (
                    {"status": "done"}
                    if kind == "complete_task"
                    else {k: v for k, v in args["updates"].items() if v is not None}
                )
                if not updates:
                    raise ValidationError("Chưa có thay đổi cần áp dụng.")
                if row.status == "cancelled" and kind == "complete_task":
                    raise ValidationError("Task đã hủy; hãy mở lại từ Tasks trước.")
                data = replace(before, **updates)
                changes.append(
                    dict(
                        entity="task",
                        id=key,
                        version=row.version,
                        before=plain(before),
                        after=plain(data),
                    )
                )
        elif kind == "propose_reschedule":
            ids = [item["event_id"] for item in args["changes"]]
            if len(set(ids)) != len(ids):
                raise ValidationError("Một event chỉ được xuất hiện một lần.")
            for item in args["changes"]:
                row = await CalendarRepository(session, owner).get(item["event_id"])
                if row.status != "confirmed":
                    raise ValidationError("Chỉ dời sự kiện confirmed.")
                before = to_record(EventData, row)
                data = replace(
                    before,
                    starts_at=timestamp(item["starts_at"]),
                    ends_at=timestamp(item["ends_at"]),
                )
                changes.append(
                    dict(
                        entity="event",
                        id=row.id,
                        version=row.version,
                        before=plain(before),
                        after=plain(data),
                    )
                )
                linked = await session.scalars(
                    select(Reminder)
                    .where(Reminder.owner_id == owner, Reminder.event_id == row.id)
                    .order_by(Reminder.id)
                )
                for reminder in linked:
                    if reminder.status not in {"active", "paused"}:
                        continue
                    busy = await session.scalar(
                        select(ReminderDelivery.id)
                        .where(
                            ReminderDelivery.reminder_id == reminder.id,
                            ReminderDelivery.status == "claimed",
                            ReminderDelivery.finished_reason.is_(None),
                        )
                        .limit(1)
                    )
                    if busy:
                        raise ValidationError("Reminder đang gửi/chờ phục hồi; hãy làm mới sau.")
                    record = ReminderRecord.from_row(reminder)
                    shifted = record.next_fire_at + (data.starts_at - before.starts_at)
                    local = shifted.astimezone(
                        zone(record.recurrence.timezone if record.recurrence else tz)
                    )
                    rule = (
                        RecurrenceRule(
                            time=local.strftime("%H:%M"),
                            timezone=record.recurrence.timezone,
                            weekday=local.weekday() if record.recurrence_type == "weekly" else None,
                        )
                        if record.recurrence
                        else None
                    )
                    shifted_data = replace(record.data(), next_fire_at=shifted, recurrence=rule)
                    reminders.append(
                        dict(
                            id=record.id,
                            updated_at=record.updated_at.isoformat(),
                            before=plain(record.data().to_storage()),
                            shifted=plain(shifted_data.to_storage()),
                        )
                    )
        else:
            raise ValidationError("Hành động không được cấp quyền.")
        for change in changes:
            if change["entity"] == "event":
                after = change["after"]
                rows = await CalendarRepository(session, owner).conflicts(
                    timestamp(after["starts_at"]),
                    timestamp(after["ends_at"]),
                    exclude_id=change["id"],
                )
                changed_ids = {c["id"] for c in changes}
                conflicts.extend(
                    dict(
                        id=r.id,
                        title=r.title,
                        version=r.version,
                        starts_at=r.starts_at.isoformat(),
                        ends_at=r.ends_at.isoformat(),
                    )
                    for r in rows
                    if r.id not in changed_ids
                )
                for other in changes:
                    if (
                        other is not change
                        and other["entity"] == "event"
                        and timestamp(other["after"]["starts_at"]) < timestamp(after["ends_at"])
                        and timestamp(other["after"]["ends_at"]) > timestamp(after["starts_at"])
                    ):
                        raise ValidationError("Các giờ mới trùng nhau; hãy chọn lại khung giờ.")
            for field, model in (
                ("project_id", self.core.projects.repository_type),
                ("task_id", TaskRepository),
                ("event_id", CalendarRepository),
            ):
                key = change["after"].get(field)
                if key:
                    ref = await model(session, owner).get(key)
                    references.append(dict(id=key, updated_at=ref.updated_at.isoformat()))
        return dict(
            args=args,
            timezone=tz,
            changes=changes,
            references=references,
            conflicts=conflicts,
            reminders=reminders,
        )

    async def propose(self, actor, kind, args, *, turn):
        owner = self.authorize(actor)
        if kind not in WRITES or len(str(turn)) > 128:
            raise ValidationError("Hành động không hợp lệ.")
        async with self.core.reminders.lock, self.transaction(write=True) as session:
            old = await session.scalar(
                select(PendingAction).where(
                    PendingAction.owner_id == owner, PendingAction.idempotency_key == str(turn)
                )
            )
            if old:
                if old.action_type != kind or old.payload_json["args"] != args:
                    raise DuplicateRequestError()
                return self.result(old)
            payload = await self.plan(session, owner, kind, args)
            row = PendingAction(
                id=str(uuid4()),
                owner_id=owner,
                idempotency_key=str(turn),
                action_type=kind,
                payload_json=payload,
                expires_at=self.clock() + timedelta(minutes=15),
                created_at=self.clock(),
                updated_at=self.clock(),
            )
            session.add(row)
            await session.flush()
            return self.result(row)

    async def bind(self, actor, key, channel, message):
        owner = self.authorize(actor)
        channel, message = discord_id(str(channel)), discord_id(str(message))
        async with self.transaction(write=True) as session:
            row = await self.get_row(session, owner, key)
            if row.message_id and (row.message_id != message or row.channel_id != channel):
                raise ApprovalInvalidError()
            row.channel_id, row.message_id = channel, message

    async def decide(self, actor, key, channel, message, *, choice):
        owner = self.authorize(actor)
        if choice not in {"keep", "shift", "reject"}:
            raise ApprovalInvalidError()
        expired = False
        async with self.core.reminders.lock, self.transaction(write=True) as session:
            row = await self.get_row(session, owner, key)
            if (
                not row.message_id
                or row.message_id != str(message)
                or row.channel_id != str(channel)
            ):
                raise ApprovalInvalidError()
            if row.status == "executed":
                return row.result_json
            if row.status != "pending":
                raise ApprovalInvalidError()
            if row.expires_at <= self.clock():
                row.status, expired = "expired", True
            elif choice == "reject":
                row.status = "rejected"
                return dict(
                    status="rejected", message="Đã bỏ đề xuất; dữ liệu nghiệp vụ giữ nguyên."
                )
            else:
                current = await self.plan(session, owner, row.action_type, row.payload_json["args"])
                if current != row.payload_json:
                    raise StaleWriteError()
                ids = []
                for change in current["changes"]:
                    values = dict(change["after"])
                    entity, record_id = change["entity"], change["id"]
                    for field in ("due_at", "starts_at", "ends_at", "next_fire_at"):
                        if field in values:
                            values[field] = timestamp(values[field])
                    if not record_id:
                        record_id = str(uuid4())
                        if entity == "task":
                            values = self.core.tasks.creation_values(TaskData(**values))
                        if entity == "event":
                            values["origin"] = "agent"
                        session.add(
                            {"task": Task, "event": CalendarEvent, "reminder": Reminder}[entity](
                                id=record_id, owner_id=owner, **values
                            )
                        )
                    else:
                        model = Task if entity == "task" else CalendarEvent
                        target = await session.scalar(
                            select(model).where(model.id == record_id, model.owner_id == owner)
                        )
                        if entity == "task":
                            values["completed_at"] = (
                                (target.completed_at or self.clock())
                                if values["status"] == "done"
                                else None
                            )
                        for field, value in values.items():
                            setattr(target, field, value)
                        target.updated_at = max(
                            self.clock(), target.updated_at + timedelta(microseconds=1)
                        )
                    ids.append(record_id)
                if choice == "shift":
                    for change in current["reminders"]:
                        target = await session.scalar(
                            select(Reminder).where(
                                Reminder.id == change["id"], Reminder.owner_id == owner
                            )
                        )
                        values = dict(change["shifted"])
                        values["next_fire_at"] = timestamp(values["next_fire_at"])
                        if values["next_fire_at"] <= self.clock():
                            raise ValidationError("Giờ nhắc sau khi dời đã qua; cần đề xuất mới.")
                        await self.core.reminders.supersede(session, owner, target.id)
                        for field, value in values.items():
                            setattr(target, field, value)
                        self.core.reminders.touch(target)
                await session.flush()
                row.status, row.result_json = (
                    "executed",
                    dict(status="executed", ids=ids, message="Đã lưu thay đổi vào database."),
                )
                session.add(
                    AuditLog(
                        owner_id=owner,
                        actor="owner",
                        action=f"agent.{row.action_type}",
                        entity_type="pending_action",
                        entity_id=row.id,
                        result="success",
                        safe_metadata_json={"count": len(ids), "reminder_policy": choice},
                    )
                )
                result = dict(row.result_json)
        if expired:
            raise ApprovalInvalidError()
        return result
