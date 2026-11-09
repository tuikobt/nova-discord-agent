"""One service bundle per bot lifecycle, including manual pending approvals."""

from app.db.repositories.dashboard_repository import DashboardRepository
from app.domain.core import TaskRecord, to_record
from app.services.calendar_service import CalendarService, local_window
from app.services.core_service import CoreService
from app.services.project_service import ProjectService
from app.services.task_service import TaskService


class SummaryService(CoreService):
    async def counts(self, actor_id, day, timezone):
        owner = self.authorize(actor_id)
        starts_at, ends_at = local_window(day, 1, timezone)
        async with self.transaction() as session:
            return await DashboardRepository(session, owner).counts(starts_at, ends_at)

    async def today_tasks(self, actor_id, day, timezone):
        owner = self.authorize(actor_id)
        _, ends_at = local_window(day, 1, timezone)
        async with self.transaction() as session:
            rows, total = await DashboardRepository(session, owner).today_tasks(ends_at)
            return tuple(to_record(TaskRecord, row) for row in rows), total


class CoreServices:
    def __init__(self, sessions, authorization):
        self.projects = ProjectService(sessions, authorization)
        self.tasks = TaskService(sessions, authorization)
        self.calendar = CalendarService(sessions, authorization)
        self.summary = SummaryService(sessions, authorization)
