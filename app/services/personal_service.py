"""Owner-confirmed memory and opt-in policy mutations, inside pending transactions."""

import re
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.agent.serialization import encode
from app.db.base import utc_now
from app.db.models import AutomationPolicy, MemoryEntry, PendingAction, User, UserSettings
from app.domain.core import resource_id
from app.domain.errors import NotFoundError, StaleWriteError, ValidationError
from app.domain.personal import (
    DEFAULTS,
    KINDS,
    MEMORY_KINDS,
    PolicyData,
    clock_time,
    memory_content,
    work_config,
)
from app.security import SecretFilter
from app.services.core_service import CoreService

PERSONAL_WRITES = frozenset(
    {
        "propose_memory",
        "update_memory",
        "delete_memory",
        "configure_work",
        "configure_automation",
        "propose_schedule_tasks",
    }
)


class PersonalService(CoreService):
    def __init__(self, sessions, authorization, core, *, clock=utc_now):
        super().__init__(sessions, authorization)
        self.core, self.clock, self.secrets = core, clock, SecretFilter()
        self.channel_validator = None
        self.on_memory_change = None
        self.memory_epoch = 0

    async def policy_rows(self, session, owner):
        rows = await session.scalars(
            select(AutomationPolicy).where(AutomationPolicy.owner_id == owner)
        )
        return {row.kind: row for row in rows}

    async def configuration(self, session, owner):
        rows = await self.policy_rows(session, owner)
        user, settings = await session.get(User, owner), await session.get(UserSettings, owner)
        work = rows.get("preferences")
        return dict(
            timezone=user.timezone,
            work=work.config_json
            if work
            else dict(workdays=[], start=None, end=None, break_minutes=10, memory_suggestions=True),
            work_version=work.version if work else 0,
            settings_updated_at=settings.updated_at.isoformat(),
            policies={
                kind: dict(
                    kind=kind,
                    enabled=rows[kind].enabled,
                    version=rows[kind].version,
                    **rows[kind].config_json,
                )
                if kind in rows
                else dict(
                    kind=kind,
                    enabled=False,
                    version=0,
                    time=DEFAULTS[kind],
                    weekday=6,
                    target="dm",
                    channel_id=None,
                    fallback=False,
                )
                for kind in KINDS
            },
        )

    async def settings(self, actor):
        owner = self.authorize(actor)
        async with self.transaction() as session:
            return await self.configuration(session, owner)

    def memory_record(self, row):
        return dict(
            id=row.id,
            content=row.content,
            kind=row.kind,
            source=row.source,
            version=row.version,
            use_for_ai=row.use_for_ai,
            confirmed=row.confirmed_by_owner,
        )

    async def memory_row(self, session, owner, key):
        resource_id(key)
        row = await session.scalar(
            select(MemoryEntry).where(
                MemoryEntry.owner_id == owner,
                MemoryEntry.id == key,
                MemoryEntry.is_deleted.is_(False),
            )
        )
        if row is None:
            raise NotFoundError()
        return row

    async def memories(self, actor, *, query="", page=0, for_ai=False):
        owner = self.authorize(actor)
        if type(page) is not int or page < 0 or not isinstance(query, str) or len(query) > 200:
            raise ValidationError("Bộ lọc memory không hợp lệ.")
        async with self.transaction() as session:
            where = [
                MemoryEntry.owner_id == owner,
                MemoryEntry.is_deleted.is_(False),
                MemoryEntry.confirmed_by_owner.is_(True),
            ]
            if query.strip():
                where.append(MemoryEntry.content.contains(query.strip(), autoescape=True))
            if for_ai:
                where.append(MemoryEntry.use_for_ai.is_(True))
            total = await session.scalar(
                select(func.count()).select_from(MemoryEntry).where(*where)
            )
            rows = await session.scalars(
                select(MemoryEntry)
                .where(*where)
                .order_by(MemoryEntry.updated_at.desc(), MemoryEntry.id)
                .limit(5)
                .offset(page * 5)
            )
            return dict(items=[self.memory_record(row) for row in rows], total=total, page=page)

    async def context(self, actor, query="", *, planning=False):
        owner = self.authorize(actor)
        async with self.transaction(write=True) as session:
            rows = list(
                await session.scalars(
                    select(MemoryEntry)
                    .where(
                        MemoryEntry.owner_id == owner,
                        MemoryEntry.is_deleted.is_(False),
                        MemoryEntry.confirmed_by_owner.is_(True),
                        MemoryEntry.use_for_ai.is_(True),
                    )
                    .order_by(MemoryEntry.updated_at.desc(), MemoryEntry.id)
                    .limit(200)
                )
            )
            terms = {w for w in re.findall(r"\w+", query.casefold()) if len(w) >= 3} - {
                "tôi",
                "bạn",
                "được",
                "những",
                "công",
                "việc",
            }
            ranked = []
            for row in rows:
                score = len(terms & set(re.findall(r"\w+", (row.content or "").casefold())))
                if planning and row.kind in {"preference", "routine"}:
                    score += 1
                if score and not self.secrets.contains(row.content):
                    ranked.append((score, row))
            ranked.sort(key=lambda pair: -pair[0])
            result = []
            for _, row in ranked[:5]:
                row.last_used_at = self.clock()
                result.append(
                    dict(id=row.id, kind=row.kind, content=row.content, version=row.version)
                )
            return result

    async def plan(self, session, owner, kind, args, *, source="manual"):
        config = await self.configuration(session, owner)
        changes, refs = [], []
        if kind in {"propose_memory", "update_memory", "delete_memory"}:
            before = None
            if kind != "propose_memory":
                row = await self.memory_row(session, owner, args["memory_id"])
                if row.version != args["expected_version"]:
                    raise StaleWriteError()
                before = self.memory_record(row)
            if kind == "delete_memory":
                after = dict(content=None, kind=before["kind"], use_for_ai=False, is_deleted=True)
            else:
                if args["kind"] not in MEMORY_KINDS:
                    raise ValidationError("Chỉ ghi nhớ preference/routine/profile đã nói rõ.")
                after = dict(
                    content=memory_content(args["content"], self.secrets),
                    kind=args["kind"],
                    use_for_ai=args["use_for_ai"],
                    is_deleted=False,
                )
                if type(after["use_for_ai"]) is not bool:
                    raise ValidationError("use_for_ai phải là boolean.")
                if before is None:
                    duplicate = await session.scalar(
                        select(MemoryEntry.id).where(
                            MemoryEntry.owner_id == owner,
                            MemoryEntry.is_deleted.is_(False),
                            MemoryEntry.kind == after["kind"],
                            MemoryEntry.content == after["content"],
                        )
                    )
                    if duplicate:
                        raise ValidationError(
                            "Thông tin này đã có trong Memory; hãy sửa mục hiện có."
                        )
            changes.append(
                dict(entity="memory", id=args.get("memory_id"), before=before, after=after)
            )
        elif kind == "configure_work":
            after = work_config(
                args["workdays"],
                args["start"],
                args["end"],
                args["break_minutes"],
                args["memory_suggestions"],
            )
            changes.append(
                dict(entity="work_settings", id="preferences", before=config["work"], after=after)
            )
            refs.append(dict(kind="preferences", version=config["work_version"]))
        elif kind == "configure_automation":
            policy = PolicyData(**args)
            after = dict(enabled=policy.enabled, **policy.config())
            changes.append(
                dict(
                    entity="automation",
                    id=policy.kind,
                    before=config["policies"][policy.kind],
                    after=after,
                )
            )
            refs.append(dict(kind=policy.kind, version=config["policies"][policy.kind]["version"]))
        elif kind == "propose_schedule_tasks":
            return await self.core.planner.validate_plan(session, owner, args, config)
        else:
            raise ValidationError("Hành động P6 không được cấp quyền.")
        return dict(
            personal_kind=kind,
            args=args,
            source=source,
            timezone=config["timezone"],
            changes=changes,
            references=refs,
            conflicts=[],
            reminders=[],
        )

    async def apply(self, session, owner, current, action):
        kind = current["personal_kind"]
        ids = []
        if kind == "propose_schedule_tasks":
            return await self.core.planner.apply(session, owner, current)
        for change in current["changes"]:
            if change["entity"] == "memory":
                key = change["id"] or str(uuid4())
                row = (
                    await self.memory_row(session, owner, key)
                    if change["id"]
                    else MemoryEntry(
                        id=key,
                        owner_id=owner,
                        kind=change["after"]["kind"],
                        confirmed_by_owner=True,
                        created_at=self.clock(),
                        version=0,
                    )
                )
                for field, value in change["after"].items():
                    setattr(row, field, value)
                row.source = current["source"] if kind == "propose_memory" else row.source
                row.version += 1
                row.updated_at = self.clock()
                session.add(row)
                ids.append(key)
                if kind == "delete_memory":
                    row.source, row.last_used_at = None, None
                    proposals = list(
                        await session.scalars(
                            select(PendingAction).where(PendingAction.owner_id == owner)
                        )
                    )
                    contents = {change["before"]["content"]}
                    for proposal in proposals:
                        if key in encode([proposal.payload_json, proposal.result_json]):
                            for item in proposal.payload_json.get("changes", []):
                                if item["entity"] == "memory":
                                    for state in (item["before"], item["after"]):
                                        if state and state.get("content"):
                                            contents.add(state["content"])
                    for proposal in proposals:
                        if proposal.id == action.id or (
                            proposal.action_type
                            in {
                                "propose_memory",
                                "update_memory",
                                "delete_memory",
                                "propose_schedule_tasks",
                            }
                            and (
                                key in encode([proposal.payload_json, proposal.result_json])
                                or any(text in encode(proposal.payload_json) for text in contents)
                            )
                        ):
                            proposal.payload_json = {"erased": True}
                            if proposal.status == "pending":
                                proposal.status = "rejected"
                self.memory_epoch += 1
                if self.on_memory_change:
                    self.on_memory_change(int(owner))
            else:
                policy_kind = change["id"]
                rows = await self.policy_rows(session, owner)
                row = rows.get(policy_kind) or AutomationPolicy(
                    id=str(uuid4()), owner_id=owner, kind=policy_kind, version=0, enabled=False
                )
                after = dict(change["after"])
                row.enabled = after.pop("enabled", False)
                row.config_json, row.version, row.updated_at = after, row.version + 1, self.clock()
                session.add(row)
                ids.append(row.id)
                if policy_kind == "preferences":
                    settings = await session.get(UserSettings, owner)
                    settings.workday_start, settings.workday_end = (
                        clock_time(after["start"]),
                        clock_time(after["end"]),
                    )
                    settings.updated_at = max(
                        self.clock(), settings.updated_at + timedelta(microseconds=1)
                    )
        await session.flush()
        return ids

    async def validate_channel(self, actor, kind, args):
        self.authorize(actor)
        if kind != "configure_automation":
            return
        policy = PolicyData(**args)
        if policy.channel_id:
            if self.channel_validator is None:
                raise ValidationError("Chưa có kết nối để kiểm tra kênh riêng.")
            await self.channel_validator(actor, policy.channel_id)
