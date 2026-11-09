from app.db.models import CalendarEvent
from app.db.repositories.core_repository import CoreRepository
from app.domain.core import EventData


class CalendarRepository(CoreRepository):
    model = CalendarEvent
    data_type = EventData

    def in_range(self, starts_at, ends_at):
        return self.query().where(
            CalendarEvent.starts_at < ends_at, CalendarEvent.ends_at > starts_at
        )

    async def list(self, starts_at, ends_at, *, status=None, page=0, page_size=10):
        query = self.in_range(starts_at, ends_at)
        if status is not None:
            query = query.where(CalendarEvent.status == status)
        return await self.page(query.order_by(CalendarEvent.starts_at), page, page_size)

    async def conflicts(self, starts_at, ends_at, *, exclude_id=None):
        query = self.in_range(starts_at, ends_at).where(CalendarEvent.status == "confirmed")
        if exclude_id is not None:
            query = query.where(CalendarEvent.id != exclude_id)
        return tuple(
            await self.session.scalars(query.order_by(CalendarEvent.starts_at, CalendarEvent.id))
        )
