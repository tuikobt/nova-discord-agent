from sqlalchemy import case, func, select

from app.db.models import Project, Task
from app.db.repositories.core_repository import CoreRepository
from app.domain.core import ProjectData, ProjectProgress


class ProjectRepository(CoreRepository):
    model = Project
    data_type = ProjectData

    async def list(self, *, status=None, page=0, page_size=10):
        query = self.query()
        if status is not None:
            query = query.where(Project.status == status)
        return await self.page(query, page, page_size)

    async def progress(self, project_id: str) -> ProjectProgress:
        await self.get(project_id)
        result = (
            await self.session.execute(
                select(func.count(), func.sum(case((Task.status == "done", 1), else_=0))).where(
                    Task.owner_id == self.owner_id,
                    Task.project_id == project_id,
                    Task.status != "cancelled",
                )
            )
        ).one()
        return ProjectProgress(done=result[1] or 0, total=result[0])
