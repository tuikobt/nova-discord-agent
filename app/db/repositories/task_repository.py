from app.db.models import Task
from app.db.repositories.core_repository import CoreRepository
from app.domain.core import TaskData


class TaskRepository(CoreRepository):
    model = Task
    data_type = TaskData
    extra_fields = frozenset({"completed_at"})

    async def list(
        self,
        *,
        status=None,
        priority=None,
        project_id=None,
        due_from=None,
        due_until=None,
        page=0,
        page_size=10,
    ):
        query = self.query()
        for column, value in (
            (Task.status, status),
            (Task.priority, priority),
            (Task.project_id, project_id),
        ):
            if value is not None:
                query = query.where(column == value)
        if due_from is not None:
            query = query.where(Task.due_at >= due_from)
        if due_until is not None:
            query = query.where(Task.due_at < due_until)
        return await self.page(query, page, page_size)
