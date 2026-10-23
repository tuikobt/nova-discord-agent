from dataclasses import replace

from app.db.repositories.project_repository import ProjectRepository
from app.domain.core import (
    Page,
    ProjectData,
    ProjectRecord,
    enum_value,
    pagination,
    resource_id,
    to_record,
)
from app.domain.enums import ProjectStatus
from app.services.core_service import CoreService


class ProjectService(CoreService):
    repository_type, data_type, record_type, kind = (
        ProjectRepository,
        ProjectData,
        ProjectRecord,
        "project",
    )

    async def list(self, actor_id: int, *, status=None, page=0, page_size=10):
        owner = self.authorize(actor_id)
        pagination(page, page_size)
        status = enum_value(ProjectStatus, status) if status is not None else None
        async with self.transaction() as session:
            rows, total = await self.repository(session, owner).list(
                status=status, page=page, page_size=page_size
            )
            return Page(
                tuple(to_record(ProjectRecord, row) for row in rows), total, page, page_size
            )

    async def progress(self, actor_id: int, project_id: str):
        owner = self.authorize(actor_id)
        resource_id(project_id)
        async with self.transaction() as session:
            return await self.repository(session, owner).progress(project_id)

    async def archive(self, actor_id: int, project_id: str, *, expected, approval_token=None):
        before = await self.get(actor_id, project_id)
        data = to_record(ProjectData, before)
        return await self.update(
            actor_id,
            project_id,
            replace(data, status="archived"),
            expected=expected,
            approval_token=approval_token,
        )

    async def gate(self, repository, owner, data, before, record_id, approval_token):
        if approval_token is not None or (
            before is not None and data.status == "archived" and before.status != "archived"
        ):
            return self.require_approval(
                owner,
                "update" if before else "create",
                record_id,
                data,
                before,
                token=approval_token,
                reason="archive_project",
            )
        return None
