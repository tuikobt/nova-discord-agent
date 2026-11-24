"""Reports are backend facts, never statistics invented by a model."""

from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.db.models import AutomationRun, CalendarEvent, Task
from app.domain.errors import NotFoundError, ValidationError
from app.domain.time import zone
from app.services.core_service import CoreService


class ReportService(CoreService):
    def __init__(self, sessions, authorization, personal, planner):
        super().__init__(sessions, authorization)
        self.personal, self.planner, self.ai = personal, planner, None

    async def build(self, actor, kind, *, period=None, background=False):
        owner = self.authorize(actor)
        if kind not in {"morning", "daily", "weekly"}:
            raise ValidationError("Loại báo cáo không hợp lệ.")
        config = await self.personal.settings(actor)
        now = self.personal.clock()
        current = period or now.astimezone(zone(config["timezone"])).date()
        first = current - timedelta(days=current.weekday()) if kind == "weekly" else current
        last = first + timedelta(days=7 if kind == "weekly" else 1)
        start = datetime.combine(first, datetime.min.time(), zone(config["timezone"]))
        end = datetime.combine(last, datetime.min.time(), zone(config["timezone"]))
        async with self.transaction() as session:
            task_scope = [Task.owner_id == owner, Task.status.in_(["todo", "doing"])]
            event_scope = [
                CalendarEvent.owner_id == owner,
                CalendarEvent.status == "confirmed",
                CalendarEvent.starts_at < end,
                CalendarEvent.ends_at > start,
            ]
            unfinished = await session.scalar(
                select(func.count()).select_from(Task).where(*task_scope)
            )
            overdue = await session.scalar(
                select(func.count()).select_from(Task).where(*task_scope, Task.due_at < now)
            )
            completed = await session.scalar(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.owner_id == owner,
                    Task.status == "done",
                    Task.completed_at >= start,
                    Task.completed_at < min(end, now),
                )
            )
            created = await session.scalar(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.owner_id == owner,
                    Task.created_at >= start,
                    Task.created_at < min(end, now),
                )
            )
            events = await session.scalar(
                select(func.count()).select_from(CalendarEvent).where(*event_scope)
            )
            tasks = list(
                await session.scalars(
                    select(Task)
                    .where(*task_scope)
                    .order_by(Task.due_at.asc().nulls_last(), Task.id)
                    .limit(5)
                )
            )
            agenda = list(
                await session.scalars(
                    select(CalendarEvent)
                    .where(*event_scope)
                    .order_by(CalendarEvent.starts_at)
                    .limit(5)
                )
            )
            result = dict(
                kind=kind,
                period_start=first.isoformat(),
                period_end=last.isoformat(),
                as_of=now.isoformat(),
                timezone=config["timezone"],
                counts=dict(
                    unfinished=unfinished,
                    overdue=overdue,
                    completed=completed,
                    created=created,
                    events=events,
                ),
                tasks=[
                    dict(id=t.id, title=t.title, due_at=t.due_at.isoformat() if t.due_at else None)
                    for t in tasks
                ],
                events=[
                    dict(
                        id=e.id,
                        title=e.title,
                        starts_at=e.starts_at.isoformat(),
                        ends_at=e.ends_at.isoformat(),
                    )
                    for e in agenda
                ],
                note="Số liệu theo trạng thái DB tại thời điểm lập; không suy ra giờ làm thực tế.",
            )
        if kind in {"morning", "weekly"}:
            target = (
                max(current, now.astimezone(zone(config["timezone"])).date())
                if kind == "morning"
                else first + timedelta(days=7)
            )
            result["planning_date"], result["planning_days"] = (
                target.isoformat(),
                1 if kind == "morning" else 7,
            )
            draft = await self.planner.draft(actor, target.isoformat(), result["planning_days"])
            result["ai_status"] = "unavailable"
            if self.ai and draft["entries"]:
                preferred = await self.ai.preference(actor, draft, background=background)
                result["ai_status"] = preferred["status"]
                if preferred["period"]:
                    draft = await self.planner.draft(
                        actor,
                        target.isoformat(),
                        result["planning_days"],
                        preferred_period=preferred["period"],
                    )
            result["plan"] = draft
        return self.personal.secrets.redact(result)

    async def history(self, actor, page=0):
        owner = self.authorize(actor)
        if type(page) is not int or page < 0:
            raise ValidationError("Trang không hợp lệ.")
        async with self.transaction() as session:
            rows = list(
                await session.scalars(
                    select(AutomationRun)
                    .where(AutomationRun.owner_id == owner)
                    .order_by(AutomationRun.created_at.desc())
                    .limit(5)
                    .offset(page * 5)
                )
            )
            total = await session.scalar(
                select(func.count())
                .select_from(AutomationRun)
                .where(AutomationRun.owner_id == owner)
            )
            return dict(
                items=[
                    dict(
                        id=r.id,
                        kind=r.kind,
                        period=r.period_key,
                        status=r.status,
                        error=r.error_code,
                        content_available=r.payload_json is not None,
                    )
                    for r in rows
                ],
                total=total,
                page=page,
            )

    async def get(self, actor, key):
        owner = self.authorize(actor)
        async with self.transaction() as session:
            row = await session.scalar(
                select(AutomationRun).where(
                    AutomationRun.owner_id == owner, AutomationRun.id == key
                )
            )
            if row is None:
                raise NotFoundError()
            return dict(
                id=row.id,
                kind=row.kind,
                status=row.status,
                error=row.error_code,
                attempts=row.attempt_count,
                payload=row.payload_json
                if row.created_at >= self.personal.clock() - timedelta(days=30)
                else None,
                channel_id=row.channel_id,
                message_id=row.discord_message_id,
            )
