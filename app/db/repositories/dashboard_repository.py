"""Owner-scoped aggregate reads; unavailable modules have no invented metrics."""

from sqlalchemy import case, func, or_, select

from app.db.models import CalendarEvent, Project, Task


class DashboardRepository:
    def __init__(self, session, owner_id: str):
        self.session, self.owner_id = session, owner_id

    async def counts(self, starts_at, ends_at):
        task_counts = (
            await self.session.execute(
                select(func.count(), func.sum(case((Task.status == "done", 1), else_=0))).where(
                    Task.owner_id == self.owner_id, Task.status != "cancelled"
                )
            )
        ).one()
        projects = await self.session.scalar(
            select(func.count())
            .select_from(Project)
            .where(Project.owner_id == self.owner_id, Project.status != "archived")
        )
        events = await self.session.scalar(
            select(func.count())
            .select_from(CalendarEvent)
            .where(
                CalendarEvent.owner_id == self.owner_id,
                CalendarEvent.status == "confirmed",
                CalendarEvent.starts_at < ends_at,
                CalendarEvent.ends_at > starts_at,
            )
        )
        return task_counts[0], task_counts[1] or 0, projects, events

    async def today_tasks(self, ends_at):
        query = select(Task).where(
            Task.owner_id == self.owner_id,
            Task.status.in_(("todo", "doing")),
            or_(Task.due_at < ends_at, Task.priority.in_(("high", "critical"))),
        )
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        priority = case((Task.priority == "critical", 0), (Task.priority == "high", 1), else_=2)
        rows = await self.session.scalars(
            query.order_by(priority, Task.due_at.asc().nullslast(), Task.id).limit(5)
        )
        return tuple(rows), total
