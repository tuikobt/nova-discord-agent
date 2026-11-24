"""Bounded planning with real task durations and deterministic conflict checks."""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import case, select

from app.agent.serialization import plain
from app.agent.tool_registry import day, timestamp
from app.db.models import CalendarEvent, MemoryEntry, Task
from app.domain.core import EventData
from app.domain.errors import ValidationError
from app.domain.time import parse_local_datetime, zone
from app.services.core_service import CoreService


class PlannerService(CoreService):
    def __init__(self, sessions, authorization, personal):
        super().__init__(sessions, authorization)
        self.personal = personal

    def bounds(self, day_value, days, timezone):
        first = day(day_value)
        if type(days) is not int or days not in {1, 7}:
            raise ValidationError("Chỉ lập kế hoạch một ngày hoặc bảy ngày.")
        now = self.personal.clock()
        local_today = now.astimezone(zone(timezone)).date()
        if not local_today <= first <= local_today + timedelta(days=365):
            raise ValidationError("Chọn ngày từ hôm nay đến tối đa một năm tới.")
        return first, first + timedelta(days=days)

    async def facts(self, session, owner, config, first, last):
        now = self.personal.clock()
        future_ids = select(CalendarEvent.task_id).where(
            CalendarEvent.owner_id == owner,
            CalendarEvent.status == "confirmed",
            CalendarEvent.ends_at > now,
            CalendarEvent.task_id.is_not(None),
        )
        query = (
            select(Task)
            .where(
                Task.owner_id == owner,
                Task.status.in_(["todo", "doing"]),
                Task.id.not_in(future_ids),
            )
            .order_by(
                Task.due_at.asc().nulls_last(),
                case({"critical": 0, "high": 1, "medium": 2, "low": 3}, value=Task.priority),
                Task.created_at,
                Task.id,
            )
        )
        tasks = list(await session.scalars(query.limit(100)))
        starts = datetime.combine(first, datetime.min.time(), zone(config["timezone"]))
        ends = datetime.combine(last, datetime.min.time(), zone(config["timezone"]))
        busy = list(
            await session.scalars(
                select(CalendarEvent)
                .where(
                    CalendarEvent.owner_id == owner,
                    CalendarEvent.status == "confirmed",
                    CalendarEvent.starts_at < ends,
                    CalendarEvent.ends_at > starts,
                )
                .order_by(CalendarEvent.starts_at, CalendarEvent.id)
            )
        )
        return tasks, busy

    def windows(self, first, last, config):
        work = config["work"]
        if not work["workdays"] or not work.get("start") or not work.get("end"):
            return []
        result = []
        current = first
        while current < last:
            if current.weekday() in work["workdays"]:
                try:
                    starts = parse_local_datetime(f"{current} {work['start']}", config["timezone"])
                    ends = parse_local_datetime(f"{current} {work['end']}", config["timezone"])
                except ValidationError:
                    current += timedelta(days=1)
                    continue  # DST gap/fold: require explicit times, do not guess.
                now = self.personal.clock().replace(second=0, microsecond=0) + timedelta(minutes=1)
                starts = max(starts, now)
                if ends > starts:
                    result.append((starts, ends))
            current += timedelta(days=1)
        return result

    async def draft(self, actor, day_value, days=1, *, preferred_period=None):
        owner = self.authorize(actor)
        async with self.transaction() as session:
            config = await self.personal.configuration(session, owner)
            first, last = self.bounds(day_value, days, config["timezone"])
            tasks, busy = await self.facts(session, owner, config, first, last)
            windows = self.windows(first, last, config)
            # AI may choose a soft preferred period; hard work bounds always win.
            if preferred_period in {"morning", "afternoon", "evening"}:
                lo, hi = {"morning": (0, 12), "afternoon": (12, 18), "evening": (18, 24)}[
                    preferred_period
                ]
                preferred, remaining = [], []
                for start, end in windows:
                    local = start.astimezone(zone(config["timezone"]))
                    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
                    a, b = (
                        max(start, midnight + timedelta(hours=lo)),
                        min(end, midnight + timedelta(hours=hi)),
                    )
                    if a < b:
                        preferred.append((a, b))
                        if start < a:
                            remaining.append((start, a))
                        if b < end:
                            remaining.append((b, end))
                    else:
                        remaining.append((start, end))
                windows = preferred + remaining
            entries, skipped = [], []
            blocks = [(row.starts_at, row.ends_at) for row in busy]
            gap = timedelta(minutes=config["work"]["break_minutes"])
            for task in tasks:
                reason = None
                if not windows:
                    reason = "Chưa cấu hình ngày/giờ làm việc hoặc không có ngày hoạt động."
                elif task.estimated_minutes is None:
                    reason = "Thiếu thời lượng; bổ sung trong Tasks rồi lập lại kế hoạch."
                elif len(entries) >= 10:
                    reason = "Đã đủ 10 task trong bản đề xuất này."
                if reason:
                    skipped.append(dict(task_id=task.id, title=task.title, reason=reason))
                    continue
                duration = timedelta(minutes=task.estimated_minutes)
                selected = None
                for start, end in windows:
                    cursor = start
                    for b_start, b_end in sorted(blocks):
                        if b_end <= cursor or b_start >= end:
                            continue
                        if cursor + duration <= min(b_start, end):
                            break
                        cursor = max(cursor, b_end)
                    deadline = (
                        task.due_at if task.due_at and task.due_at > self.personal.clock() else end
                    )
                    if cursor + duration <= min(end, deadline):
                        selected = cursor
                        break
                if selected is None:
                    skipped.append(
                        dict(
                            task_id=task.id,
                            title=task.title,
                            reason="Không đủ slot liên tục trước deadline; chưa tự chia nhỏ task.",
                        )
                    )
                    continue
                finish = selected + duration
                entries.append(
                    dict(
                        task_id=task.id,
                        title=task.title,
                        starts_at=selected.isoformat(),
                        ends_at=finish.isoformat(),
                    )
                )
                blocks.append((selected - gap, finish + gap))
            return dict(
                date=first.isoformat(),
                days=days,
                timezone=config["timezone"],
                entries=entries,
                unscheduled=skipped,
                capped=len(tasks) == 100,
                source="NOVA database",
                preferred_period=preferred_period,
            )

    async def validate_plan(self, session, owner, args, config):
        first, last = self.bounds(args["date"], args["days"], config["timezone"])
        windows = self.windows(first, last, config)
        if not windows:
            raise ValidationError("Hãy cấu hình ngày và giờ làm việc trước khi xếp task.")
        tasks, busy = await self.facts(session, owner, config, first, last)
        available = {row.id: row for row in tasks}
        changes, chosen, seen = [], [], set()
        for entry in args["entries"]:
            task = available.get(entry["task_id"])
            if task is None or task.id in seen or task.estimated_minutes is None:
                raise ValidationError(
                    "Task đã đổi trạng thái/có lịch hoặc chưa có thời lượng. Làm mới kế hoạch."
                )
            seen.add(task.id)
            starts, ends = timestamp(entry["starts_at"]), timestamp(entry["ends_at"])
            if starts <= self.personal.clock() or ends - starts != timedelta(
                minutes=task.estimated_minutes
            ):
                raise ValidationError("Giờ đã qua hoặc thời lượng không đúng với task.")
            if not any(start <= starts < ends <= end for start, end in windows):
                raise ValidationError("Block nằm ngoài ngày/giờ làm việc đã cấu hình.")
            if task.due_at and task.due_at > self.personal.clock() and ends > task.due_at:
                raise ValidationError("Block vượt deadline của task.")
            if any(row.starts_at < ends and row.ends_at > starts for row in busy):
                raise ValidationError("Có lịch confirmed trùng giờ. Hãy làm mới kế hoạch.")
            gap = timedelta(minutes=config["work"]["break_minutes"])
            if any(a < ends + gap and b + gap > starts for a, b in chosen):
                raise ValidationError("Các block mới trùng hoặc thiếu khoảng nghỉ.")
            chosen.append((starts, ends))
            after = EventData(title=task.title, starts_at=starts, ends_at=ends, task_id=task.id)
            changes.append(
                dict(
                    entity="event",
                    id=None,
                    before=None,
                    after=plain(after),
                    task_version=task.version,
                )
            )
        memories = list(
            await session.scalars(
                select(MemoryEntry)
                .where(
                    MemoryEntry.owner_id == owner,
                    MemoryEntry.is_deleted.is_(False),
                    MemoryEntry.use_for_ai.is_(True),
                    MemoryEntry.confirmed_by_owner.is_(True),
                )
                .order_by(MemoryEntry.id)
            )
        )
        refs = dict(
            work_version=config["work_version"],
            settings_updated_at=config["settings_updated_at"],
            memory_versions=[dict(id=m.id, version=m.version) for m in memories],
            busy=[dict(id=e.id, version=e.version) for e in busy],
        )
        return dict(
            personal_kind="propose_schedule_tasks",
            args=args,
            timezone=config["timezone"],
            changes=changes,
            references=refs,
            conflicts=[],
            reminders=[],
        )

    async def apply(self, session, owner, current):
        ids = []
        for item in current["changes"]:
            values = dict(item["after"])
            values["starts_at"], values["ends_at"] = (
                timestamp(values["starts_at"]),
                timestamp(values["ends_at"]),
            )
            key = str(uuid4())
            session.add(CalendarEvent(id=key, owner_id=owner, origin="agent", **values))
            ids.append(key)
        await session.flush()
        return ids
