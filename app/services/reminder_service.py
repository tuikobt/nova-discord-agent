"""Owner-scoped reminder mutations and notification actions, with explicit approvals."""

import asyncio
from dataclasses import replace
from datetime import time, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.db.base import utc_now
from app.db.models import Reminder, ReminderDelivery, UserSettings
from app.db.repositories.calendar_repository import CalendarRepository
from app.db.repositories.reminder_repository import ReminderRepository
from app.db.repositories.task_repository import TaskRepository
from app.domain.approvals import ApprovalStore
from app.domain.core import Page, enum_value, pagination, resource_id, text_value
from app.domain.enums import ReminderStatus
from app.domain.errors import DuplicateRequestError, StaleWriteError, ValidationError
from app.domain.reminder_delivery import (
    ACTION_TTL,
    DeliveryRecord,
    NotificationPreferences,
    ReminderRecord,
    next_occurrence,
)
from app.domain.reminders import RecurrenceRule, ReminderData, discord_id
from app.domain.time import as_utc
from app.services.core_service import CoreService


class ReminderService(CoreService):
    repository_type = ReminderRepository
    kind = "reminder"

    def __init__(self, sessions, authorization, *, clock=utc_now, channel_validator=None):
        super().__init__(sessions, authorization, approvals=ApprovalStore(clock=clock))
        self.clock, self.channel_validator = clock, channel_validator
        # Shared by UI mutations and dispatcher, including the external send window.
        self.lock = asyncio.Lock()

    def now(self):
        return as_utc(self.clock())

    def touch(self, row):
        row.updated_at = max(self.now(), row.updated_at + timedelta(microseconds=1))
        return row.updated_at

    def data(self, value):
        if type(value) is not ReminderData:
            raise ValidationError("Dữ liệu lời nhắc không đúng loại.")
        rule = (
            RecurrenceRule.from_config(value.recurrence.to_config()) if value.recurrence else None
        )
        return replace(value, recurrence=rule)

    async def get(self, actor_id, key):
        owner = self.authorize(actor_id)
        resource_id(key)
        async with self.transaction() as session:
            return ReminderRecord.from_row(await self.repository(session, owner).get(key))

    async def list(self, actor_id, *, status=None, page=0, page_size=5):
        owner = self.authorize(actor_id)
        pagination(page, page_size)
        if status is not None:
            status = enum_value(ReminderStatus, status)
        async with self.transaction() as session:
            rows, count = await self.repository(session, owner).list(
                status=status, page=page, page_size=page_size
            )
            return Page(tuple(ReminderRecord.from_row(row) for row in rows), count, page, page_size)

    async def history(self, actor_id, key):
        owner = self.authorize(actor_id)
        resource_id(key)
        async with self.transaction() as session:
            return tuple(
                DeliveryRecord.from_row(row)
                for row in await self.repository(session, owner).history(key)
            )

    async def preferences(self, actor_id):
        owner = self.authorize(actor_id)
        async with self.transaction() as session:
            return await self.repository(session, owner).preferences()

    async def validate_channel(self, actor_id, channel_id):
        self.authorize(actor_id)
        discord_id(channel_id)
        if self.channel_validator is None:
            raise ValidationError("Chưa có kết nối để kiểm tra kênh riêng.")
        await self.channel_validator(actor_id, channel_id)

    async def references(self, session, owner, data):
        if data.task_id:
            await TaskRepository(session, owner).get(data.task_id)
        if data.event_id:
            await CalendarRepository(session, owner).get(data.event_id)
        if data.delivery_target == "channel":
            preferences = await self.repository(session, owner).preferences()
            if data.channel_id != preferences.channel_id:
                raise ValidationError("Chỉ dùng kênh riêng đã được duyệt trong Cài đặt gửi.")

    async def create(self, actor_id, data, *, request_id):
        owner = self.authorize(actor_id)
        data = self.data(data)
        key = str(uuid5(NAMESPACE_URL, f"nova:reminder:{owner}:{text_value(request_id, 128)}"))
        if data.delivery_target == "channel":
            await self.validate_channel(actor_id, data.channel_id)
        async with self.lock, self.transaction(write=True) as session:
            repository = self.repository(session, owner)
            row = await repository.get(key, required=False)
            if row is not None:
                if ReminderRecord.from_row(row).data() != data:
                    raise DuplicateRequestError()
                return ReminderRecord.from_row(row)
            data.validate_create(now=self.now())
            await self.references(session, owner, data)
            row = Reminder(
                id=key,
                owner_id=owner,
                created_at=self.now(),
                updated_at=self.now(),
                **data.to_storage(),
            )
            session.add(row)
            await session.flush()
            result = ReminderRecord.from_row(row)
        return result

    async def supersede(self, session, owner, key):
        # The caller already holds the writer transaction and process send lock.
        await self.repository(session, owner).get(key)
        rows = await session.scalars(
            select(ReminderDelivery).where(
                ReminderDelivery.reminder_id == key,
                ReminderDelivery.status != "sent",
                ReminderDelivery.finished_reason.is_(None),
            )
        )
        for row in rows:
            row.status, row.finished_reason, row.claim_token = "failed", "superseded", None

    async def update(self, actor_id, key, data, *, expected, approval_token=None):
        owner = self.authorize(actor_id)
        resource_id(key)
        data = self.data(data)
        if data.delivery_target == "channel" and data.status == "active":
            await self.validate_channel(actor_id, data.channel_id)
        token = None
        async with self.lock, self.transaction(write=True) as session:
            repository = self.repository(session, owner)
            row = await repository.get(key)
            before = ReminderRecord.from_row(row)
            self.check_expected(before, expected)
            if data == before.data():
                return before
            if before.status in ("done", "cancelled") and data.status != "cancelled":
                raise ValidationError("Lời nhắc đã kết thúc; hãy tạo lời nhắc mới.")
            if data.status == "active":
                await self.references(session, owner, data)
                data.validate_create(now=self.now())
            token = self.require_approval(
                owner, "update", key, data, before, token=approval_token, reason="change_reminder"
            )
            await self.supersede(session, owner, key)
            for name, value in data.to_storage().items():
                setattr(row, name, value)
            self.touch(row)
            await session.flush()
            result = ReminderRecord.from_row(row)
        self.approvals.consume(token)
        return result

    async def set_status(self, actor_id, key, status, *, expected, approval_token=None):
        self.authorize(actor_id)
        if status not in ("active", "paused", "cancelled"):
            raise ValidationError("Trạng thái không hợp lệ.")
        before = await self.get(actor_id, key)
        data = replace(before.data(), status=status)
        if status == "active" and before.status == "paused" and data.next_fire_at <= self.now():
            fire = (
                next_occurrence(data.recurrence, self.now())
                if data.recurrence
                else self.now() + timedelta(minutes=1)
            )
            data = replace(data, next_fire_at=fire)
        return await self.update(
            actor_id, key, data, expected=expected, approval_token=approval_token
        )

    async def configure(
        self,
        actor_id,
        *,
        dm_enabled,
        channel_id,
        quiet_start,
        quiet_end,
        expected,
        approval_token=None,
    ):
        owner = self.authorize(actor_id)
        if type(dm_enabled) is not bool:
            raise ValidationError("Cài đặt DM không hợp lệ.")
        if (quiet_start is None) != (quiet_end is None) or (
            quiet_start is not None
            and (
                type(quiet_start) is not time
                or type(quiet_end) is not time
                or quiet_start.tzinfo is not None
                or quiet_end.tzinfo is not None
                or quiet_start == quiet_end
            )
        ):
            raise ValidationError("Nhập cả hai giờ yên lặng local khác nhau, hoặc bỏ trống cả hai.")
        if channel_id is not None:
            await self.validate_channel(actor_id, channel_id)
        async with self.lock, self.transaction(write=True) as session:
            before = await self.repository(session, owner).preferences()
            if before.updated_at != as_utc(expected):
                raise StaleWriteError()
            after = NotificationPreferences(
                before.timezone, dm_enabled, channel_id, quiet_start, quiet_end, before.updated_at
            )
            token = self.require_approval(
                owner,
                "preferences",
                "settings",
                after,
                before,
                token=approval_token,
                reason="notifications",
            )
            row = await session.get(UserSettings, owner)
            row.dm_notifications_enabled, row.fallback_channel_id = dm_enabled, channel_id
            row.quiet_start, row.quiet_end = quiet_start, quiet_end
            self.touch(row)
            result = replace(after, updated_at=row.updated_at)
        self.approvals.consume(token)
        return result

    async def notification_action(self, actor_id, delivery_id, message_id, action):
        owner = self.authorize(actor_id)
        resource_id(delivery_id)
        if action not in ("done", "snooze"):
            raise ValidationError("Thao tác thông báo không hợp lệ.")
        async with self.lock, self.transaction(write=True) as session:
            repository = self.repository(session, owner)
            delivery = await repository.delivery(delivery_id)
            reminder = await repository.get(delivery.reminder_id)
            if delivery.status != "sent" or delivery.discord_message_id != str(message_id):
                raise ValidationError("Thông báo không hợp lệ hoặc chưa được ghi nhận đã gửi.")
            if delivery.acknowledged_at is not None:
                raise ValidationError(
                    "Thông báo đã được xử lý. Mở Reminders để xem trạng thái mới."
                )
            if (
                delivery.sent_at is None
                or self.now() - delivery.sent_at > ACTION_TTL
                or reminder.updated_at > delivery.sent_at
                or reminder.status in ("paused", "cancelled")
            ):
                raise StaleWriteError()
            if action == "snooze":
                fire = self.now() + timedelta(minutes=15)
                collision = await session.scalar(
                    select(ReminderDelivery.id).where(
                        ReminderDelivery.reminder_id == reminder.id,
                        ReminderDelivery.scheduled_fire_at == fire,
                    )
                )
                if collision is not None or (
                    reminder.status == "active" and reminder.next_fire_at == fire
                ):
                    raise ValidationError("Đã có lần nhắc ở thời điểm đó; không tạo trùng.")
                session.add(
                    ReminderDelivery(
                        reminder_id=reminder.id,
                        scheduled_fire_at=fire,
                        delivery_kind="snooze",
                        parent_delivery_id=delivery.id,
                    )
                )
            elif reminder.task_id:
                task = await TaskRepository(session, owner).get(reminder.task_id)
                if task.status == "cancelled":
                    raise StaleWriteError()
                if task.status != "done":
                    task.status, task.completed_at = "done", self.now()
            delivery.acknowledged_at = self.now()
            await session.flush()
            return ReminderRecord.from_row(reminder)

    async def notification_reminder(self, actor_id, delivery_id, message_id):
        owner = self.authorize(actor_id)
        resource_id(delivery_id)
        async with self.transaction() as session:
            repository = self.repository(session, owner)
            delivery = await repository.delivery(delivery_id)
            if (
                delivery.status != "sent"
                or delivery.discord_message_id != str(message_id)
                or delivery.sent_at is None
                or self.now() - delivery.sent_at > ACTION_TTL
            ):
                raise StaleWriteError()
            return ReminderRecord.from_row(await repository.get(delivery.reminder_id))
