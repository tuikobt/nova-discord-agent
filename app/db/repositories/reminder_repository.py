from sqlalchemy import func, or_, select

from app.db.models import Reminder, ReminderDelivery, User, UserSettings
from app.domain.errors import NotFoundError
from app.domain.reminder_delivery import NotificationPreferences


class ReminderRepository:
    def __init__(self, session, owner_id):
        self.session, self.owner_id = session, owner_id

    async def get(self, key, *, required=True):
        row = await self.session.scalar(
            select(Reminder).where(Reminder.id == key, Reminder.owner_id == self.owner_id)
        )
        if row is None and required:
            raise NotFoundError()
        return row

    async def list(self, *, status=None, page=0, page_size=5):
        query = select(Reminder).where(Reminder.owner_id == self.owner_id)
        if status is not None:
            query = query.where(Reminder.status == status)
        count = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(Reminder.next_fire_at, Reminder.id)
            .offset(page * page_size)
            .limit(page_size)
        )
        return tuple(rows), count

    async def delivery(self, key, *, required=True):
        row = await self.session.scalar(
            select(ReminderDelivery)
            .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
            .where(ReminderDelivery.id == key, Reminder.owner_id == self.owner_id)
        )
        if row is None and required:
            raise NotFoundError()
        return row

    async def history(self, key, *, limit=5):
        await self.get(key)
        return tuple(
            await self.session.scalars(
                select(ReminderDelivery)
                .where(ReminderDelivery.reminder_id == key)
                .order_by(ReminderDelivery.scheduled_fire_at.desc(), ReminderDelivery.id)
                .limit(limit)
            )
        )

    async def preferences(self):
        user = await self.session.get(User, self.owner_id)
        settings = await self.session.get(UserSettings, self.owner_id)
        if user is None or settings is None:
            raise NotFoundError()
        return NotificationPreferences(
            user.timezone,
            settings.dm_notifications_enabled,
            settings.fallback_channel_id,
            settings.quiet_start,
            settings.quiet_end,
            settings.updated_at,
        )

    async def due_reminders(self, now, limit=25):
        return tuple(
            await self.session.scalars(
                select(Reminder)
                .where(
                    Reminder.owner_id == self.owner_id,
                    Reminder.status == "active",
                    Reminder.next_fire_at <= now,
                )
                .order_by(Reminder.next_fire_at, Reminder.id)
                .limit(limit)
            )
        )

    async def due_deliveries(self, now, limit=25):
        return tuple(
            await self.session.scalars(
                select(ReminderDelivery)
                .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
                .where(
                    Reminder.owner_id == self.owner_id,
                    ReminderDelivery.status.in_(("pending", "failed", "claimed")),
                    ReminderDelivery.finished_reason.is_(None),
                    ReminderDelivery.scheduled_fire_at <= now,
                    or_(ReminderDelivery.retry_at.is_(None), ReminderDelivery.retry_at <= now),
                )
                .order_by(ReminderDelivery.scheduled_fire_at, ReminderDelivery.id)
                .limit(limit)
            )
        )
