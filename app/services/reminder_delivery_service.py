"""Durable occurrence state machine. Caller serializes sends with ReminderService.lock."""

from uuid import uuid4

from sqlalchemy import select

from app.db.models import ReminderDelivery
from app.domain.errors import StaleWriteError
from app.domain.reminder_delivery import (
    CATCH_UP,
    CLAIM_LEASE,
    MAX_ATTEMPTS,
    RETRY_DELAYS,
    DeliveryClaim,
    DeliveryRecord,
    ReminderRecord,
    next_occurrence,
    quiet_until,
)
from app.domain.reminders import discord_id


class ReminderDeliveryService:
    def __init__(self, reminders):
        self.reminders = reminders

    def owner(self, actor_id):
        return self.reminders.authorize(actor_id)

    def advance(self, reminder, now, *, outcome):
        if outcome not in ("sent", "overdue"):
            reminder.status = "paused"
        elif reminder.recurrence_config_json is not None:
            record = ReminderRecord.from_row(reminder)
            reminder.next_fire_at = next_occurrence(
                record.recurrence, max(now, reminder.next_fire_at)
            )
        else:
            reminder.status = "done" if outcome == "sent" else "paused"
        return self.reminders.touch(reminder)

    async def enqueue(self, actor_id):
        owner = self.owner(actor_id)
        service, now = self.reminders, self.reminders.now()
        async with service.transaction(write=True) as session:
            repository = service.repository(session, owner)
            for reminder in await repository.due_reminders(now):
                row = await session.scalar(
                    select(ReminderDelivery).where(
                        ReminderDelivery.reminder_id == reminder.id,
                        ReminderDelivery.scheduled_fire_at == reminder.next_fire_at,
                    )
                )
                if row is None:
                    row = ReminderDelivery(
                        reminder_id=reminder.id, scheduled_fire_at=reminder.next_fire_at
                    )
                    session.add(row)
                elif row.status == "sent":
                    self.advance(reminder, now, outcome="sent")
                    continue
                elif row.finished_reason == "superseded":
                    row.status, row.finished_reason = "pending", None
                    row.retry_at, row.claim_token, row.attempt_count = None, None, 0
                if (
                    row.finished_reason is None
                    and row.retry_at is None
                    and now - row.scheduled_fire_at > CATCH_UP
                ):
                    row.status, row.finished_reason = "failed", "overdue"
                    self.advance(reminder, now, outcome="overdue")

    async def due(self, actor_id):
        owner = self.owner(actor_id)
        async with self.reminders.transaction() as session:
            return tuple(
                row.id
                for row in await self.reminders.repository(session, owner).due_deliveries(
                    self.reminders.now()
                )
            )

    async def claim(self, actor_id, key):
        owner = self.owner(actor_id)
        service, now = self.reminders, self.reminders.now()
        async with service.transaction(write=True) as session:
            repository = service.repository(session, owner)
            delivery = await repository.delivery(key)
            reminder = await repository.get(delivery.reminder_id)
            if (
                delivery.scheduled_fire_at > now
                or delivery.finished_reason is not None
                or delivery.status == "sent"
                or (delivery.retry_at is not None and delivery.retry_at > now)
            ):
                return None
            if reminder.status != "active" and not (
                reminder.status == "done" and delivery.delivery_kind == "snooze"
            ):
                delivery.status, delivery.finished_reason = "failed", "superseded"
                return None
            if delivery.status == "claimed" and (
                delivery.claimed_at is not None and delivery.claimed_at + CLAIM_LEASE > now
            ):
                return None
            if delivery.attempt_count >= MAX_ATTEMPTS:
                delivery.status, delivery.finished_reason = "failed", "exhausted"
                if delivery.delivery_kind == "scheduled":
                    self.advance(reminder, now, outcome="exhausted")
                return None
            if now - (delivery.retry_at or delivery.scheduled_fire_at) > CATCH_UP:
                delivery.status, delivery.finished_reason = "failed", "overdue"
                if delivery.delivery_kind == "scheduled":
                    self.advance(reminder, now, outcome="overdue")
                return None
            preferences = await repository.preferences()
            defer = quiet_until(
                now, preferences.timezone, preferences.quiet_start, preferences.quiet_end
            )
            if defer is not None:
                delivery.status, delivery.retry_at, delivery.claim_token = "pending", defer, None
                return None
            delivery.status, delivery.claim_token = "claimed", str(uuid4())
            delivery.claimed_at, delivery.retry_at = now, now + CLAIM_LEASE
            delivery.attempt_count += 1
            await session.flush()
            return DeliveryClaim(
                ReminderRecord.from_row(reminder), DeliveryRecord.from_row(delivery), preferences
            )

    async def finish(self, actor_id, claim, *, message_id=None, failure=None):
        owner = self.owner(actor_id)
        service, now = self.reminders, self.reminders.now()
        if message_id is not None:
            discord_id(str(message_id))
        async with service.transaction(write=True) as session:
            repository = service.repository(session, owner)
            delivery = await repository.delivery(claim.delivery.id)
            reminder = await repository.get(delivery.reminder_id)
            if delivery.status != "claimed" or delivery.claim_token != claim.delivery.claim_token:
                raise StaleWriteError()
            if failure is None:
                if message_id is None:
                    raise ValueError("Successful delivery requires a Discord message ID")
                delivery.status, delivery.discord_message_id = "sent", str(message_id)
                delivery.retry_at, delivery.last_error_code = None, None
                stamp = now
                if (
                    delivery.delivery_kind == "scheduled"
                    and reminder.status == "active"
                    and reminder.updated_at == claim.reminder.updated_at
                ):
                    stamp = self.advance(reminder, now, outcome="sent")
                delivery.sent_at = max(stamp, reminder.updated_at)
            else:
                delivery.status, delivery.last_error_code = "failed", failure.code
                if failure.permanent or delivery.attempt_count >= MAX_ATTEMPTS:
                    delivery.finished_reason = "blocked" if failure.permanent else "exhausted"
                    delivery.retry_at = None
                    if delivery.delivery_kind == "scheduled":
                        self.advance(reminder, now, outcome=delivery.finished_reason)
                else:
                    delivery.retry_at = now + RETRY_DELAYS[delivery.attempt_count - 1]
            delivery.claim_token = None
