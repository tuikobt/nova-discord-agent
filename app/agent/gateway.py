"""No model-derived identity, arbitrary queries, or approval operations."""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.agent.serialization import plain
from app.agent.tool_registry import WRITES, day, timestamp, validate
from app.db.models import User, UserSettings
from app.domain.connections import CONNECTION_WRITES
from app.domain.errors import ValidationError
from app.services.calendar_service import local_window
from app.services.core_service import CoreService


class ToolGateway(CoreService):
    def __init__(self, sessions, authorization, core, pending):
        super().__init__(sessions, authorization)
        self.core, self.pending = core, pending

    async def preferences(self, actor, keys):
        owner = self.authorize(actor)
        async with self.transaction() as session:
            user, settings = await session.get(User, owner), await session.get(UserSettings, owner)
            return {
                k: plain(getattr(user if k in {"timezone", "locale"} else settings, k))
                for k in keys
            }

    async def call(self, actor, name, args, *, turn, allowed):
        self.authorize(actor)
        if name in CONNECTION_WRITES:
            raise ValidationError(
                "Quản lý kết nối tại Cài đặt; AI không được tự thay phạm vi hoặc quyền."
            )
        if name not in allowed:
            raise ValidationError("Tool không được mở trong lượt này.")
        args = validate(name, args)
        if name in WRITES:
            return dict(pending=await self.pending.propose(actor, name, args, turn=turn))
        if name == "search_memory":
            return await self.core.personal.memories(actor, query=args["query"], for_ai=True)
        if name == "plan_tasks":
            return await self.core.planner.draft(actor, args["date"], args["days"])
        core = self.core
        tz = (await self.preferences(actor, ["timezone"]))["timezone"]
        if name == "list_tasks":
            return plain(
                await core.tasks.list(
                    actor,
                    status=args["status"],
                    project_id=args["project_id"],
                    due_from=timestamp(args["due_from"]),
                    due_until=timestamp(args["due_to"]),
                    page_size=args["limit"],
                )
            )
        if name == "get_task":
            return plain(await core.tasks.get(actor, args["task_id"]))
        if name == "list_projects":
            return plain(await core.projects.list(actor, status=args["status"], page_size=20))
        if name == "list_reminders":
            return plain(await core.reminders.list(actor, status=args["status"], page_size=20))
        if name == "get_preferences":
            return await self.preferences(actor, args["keys"])
        if name == "list_events":
            first, last = day(args["date_from"]), day(args["date_to"])
            if not 0 <= (last - first).days <= 30:
                raise ValidationError("Khoảng lịch tối đa 31 ngày, gồm ngày cuối.")
            starts = local_window(first, 1, tz)[0]
            ends = local_window(last, 1, tz)[1]
            return plain(await core.calendar.list(actor, starts, ends, page_size=20))
        current = day(args["date"])
        if name in {"get_today_overview", "suggest_next_action"}:
            events = await core.calendar.list_day(
                actor, current, timezone=tz, status="confirmed", page_size=20
            )
            tasks, total = await core.summary.today_tasks(actor, current, tz)
            return dict(
                date=current.isoformat(),
                timezone=tz,
                counts=plain(await core.summary.counts(actor, current, tz)),
                tasks=plain(tasks),
                task_total=total,
                events=plain(events),
                source="NOVA database",
                note=(
                    "Task chưa xong: đến hạn/quá hạn hoặc ưu tiên cao. "
                    "Chỉ preview khi vượt giới hạn; không tự đổi lịch."
                ),
            )
        if name == "find_free_slots":
            starts, ends = local_window(current, 1, tz)
            # Query all confirmed intervals for this bounded day, not a truncated page.
            owner = str(actor)
            async with self.transaction() as session:
                preferences = await session.get(UserSettings, owner)
                if preferences.workday_start and preferences.workday_end:
                    starts = datetime.combine(current, preferences.workday_start, starts.tzinfo)
                    ends = datetime.combine(current, preferences.workday_end, starts.tzinfo)
                    if ends <= starts:
                        raise ValidationError("Khung giờ làm việc chưa hợp lệ.")
                from app.db.models import CalendarEvent

                rows = list(
                    await session.scalars(
                        select(CalendarEvent)
                        .where(
                            CalendarEvent.owner_id == owner,
                            CalendarEvent.status == "confirmed",
                            CalendarEvent.starts_at < ends,
                            CalendarEvent.ends_at > starts,
                        )
                        .order_by(CalendarEvent.starts_at)
                    )
                )
                slots, cursor = [], starts
                for row in rows:
                    if row.starts_at - cursor >= timedelta(minutes=args["min_minutes"]):
                        slots.append(
                            dict(starts_at=cursor.isoformat(), ends_at=row.starts_at.isoformat())
                        )
                    cursor = max(cursor, row.ends_at)
                if ends - cursor >= timedelta(minutes=args["min_minutes"]):
                    slots.append(dict(starts_at=cursor.isoformat(), ends_at=ends.isoformat()))
                return dict(
                    date=current.isoformat(),
                    timezone=tz,
                    workday_configured=bool(preferences.workday_start and preferences.workday_end),
                    slots=slots[:20],
                    total=len(slots),
                )
        raise ValidationError("Tool không tồn tại.")
