from dataclasses import fields, replace

from app.db.base import utc_now
from app.db.repositories.project_repository import ProjectRepository
from app.db.repositories.task_repository import TaskRepository
from app.domain.core import (
    Page,
    TaskData,
    TaskRecord,
    data_values,
    enum_value,
    pagination,
    resource_id,
    to_record,
)
from app.domain.enums import TaskPriority, TaskStatus
from app.domain.errors import ValidationError
from app.domain.time import as_utc
from app.services.core_service import CoreService


class TaskService(CoreService):
    repository_type, data_type, record_type, kind = TaskRepository, TaskData, TaskRecord, "task"

    async def validate_references(self, session, owner, data):
        if data.project_id is not None:
            await ProjectRepository(session, owner).get(data.project_id)

    def creation_values(self, data):
        return {**data_values(data), "completed_at": utc_now() if data.status == "done" else None}

    def update_values(self, data, before):
        completed = before.completed_at or utc_now() if data.status == "done" else None
        return {**data_values(data), "completed_at": completed}

    async def list(
        self,
        actor_id: int,
        *,
        status=None,
        priority=None,
        project_id=None,
        due_from=None,
        due_until=None,
        page=0,
        page_size=10,
    ):
        owner = self.authorize(actor_id)
        pagination(page, page_size)
        status = enum_value(TaskStatus, status) if status is not None else None
        priority = enum_value(TaskPriority, priority) if priority is not None else None
        if project_id is not None:
            resource_id(project_id)
        due_from = as_utc(due_from) if due_from is not None else None
        due_until = as_utc(due_until) if due_until is not None else None
        if due_from is not None and due_until is not None and due_until <= due_from:
            raise ValidationError("Khoảng deadline không hợp lệ.")
        async with self.transaction() as session:
            if project_id is not None:
                await ProjectRepository(session, owner).get(project_id)
            rows, total = await self.repository(session, owner).list(
                status=status,
                priority=priority,
                project_id=project_id,
                due_from=due_from,
                due_until=due_until,
                page=page,
                page_size=page_size,
            )
            return Page(tuple(to_record(TaskRecord, row) for row in rows), total, page, page_size)

    async def set_status(
        self, actor_id: int, task_id: str, status: str, *, expected, approval_token=None
    ):
        before = await self.get(actor_id, task_id)
        data = TaskData(**{field.name: getattr(before, field.name) for field in fields(TaskData)})
        return await self.update(
            actor_id,
            task_id,
            replace(data, status=status),
            expected=expected,
            approval_token=approval_token,
        )

    async def gate(self, repository, owner, data, before, record_id, approval_token):
        if approval_token is not None or (
            before is not None and data.status == "cancelled" and before.status != "cancelled"
        ):
            return self.require_approval(
                owner,
                "update" if before else "create",
                record_id,
                data,
                before,
                token=approval_token,
                reason="cancel_task",
            )
        return None
