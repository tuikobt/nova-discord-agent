import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_agent import CONFIG, NOW, TASK_ARGS, bind, bundle, response

from app.agent.orchestrator import AgentOrchestrator
from app.agent.personal_ai import PersonalAI
from app.agent.serialization import encode
from app.db.models import CalendarEvent, MemoryEntry, PendingAction
from app.discord_bot.agent_controller import preview_pages
from app.domain.authorization import AuthorizationError
from app.domain.core import EventData, TaskData
from app.domain.errors import StaleWriteError, StorageError, ValidationError
from app.domain.personal import PolicyData, clock_time, memory_content, work_config
from app.domain.time import zone
from app.security import SecretFilter

MEMORY = dict(content="Tôi thích học Python vào buổi sáng", kind="preference", use_for_ai=True)
WORK = dict(
    workdays=list(range(7)), start="09:00", end="17:00", break_minutes=10, memory_suggestions=True
)


async def approve(env, pending, kind, args):
    proposal = await pending.propose(env.owner, kind, args, turn=str(uuid4()), source="owner:ui")
    await bind(pending, env.owner, proposal)
    return await pending.decide(env.owner, proposal["id"], "123", "456", choice="keep")


def personal_bundle(env):
    core, pending, gateway, usage = bundle(env)
    core.personal.clock = lambda: NOW
    return core, pending, gateway, usage


def test_memory_confirmed_versioned_searchable_revocable_and_erased(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            candidate = await pending.propose(
                env.owner, "propose_memory", MEMORY, turn="candidate", source="dm:111"
            )
            assert not (await core.personal.memories(env.owner))["items"]
            assert not await core.personal.context(env.owner, "Python")
            await bind(pending, env.owner, candidate)
            receipt = await pending.decide(env.owner, candidate["id"], "123", "456", choice="keep")
            key = receipt["ids"][0]
            memory = (await core.personal.memories(env.owner, query="Python"))["items"][0]
            assert memory["id"] == key and memory["source"] == "dm:111"
            assert (await core.personal.context(env.owner, "Python"))[0]["id"] == key
            args = dict(memory_id=key, expected_version=1, **MEMORY)
            stale = await pending.propose(env.owner, "update_memory", args, turn="old")
            await bind(pending, env.owner, stale)
            await approve(env, pending, "update_memory", {**args, "use_for_ai": False})
            assert not await core.personal.context(env.owner, "Python")
            assert not (await core.personal.memories(env.owner, for_ai=True))["items"]
            with pytest.raises(StaleWriteError):
                await pending.decide(env.owner, stale["id"], "123", "456", choice="keep")
            await approve(env, pending, "delete_memory", dict(memory_id=key, expected_version=2))
            assert (await core.personal.memories(env.owner))["total"] == 0
            async with env.database.sessions() as session:
                row = await session.get(MemoryEntry, key)
                assert row.content is None and row.source is None and row.is_deleted
                proposals = list(await session.scalars(select(PendingAction)))
                assert MEMORY["content"] not in encode([p.payload_json for p in proposals])
                assert all("ĐỀ XUẤT" not in preview_pages(pending.result(p))[0] for p in proposals)

    asyncio.run(scenario())


def test_memory_owner_scope_context_limit_and_no_unapproved_inference(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            for index in range(7):
                await approve(
                    env, pending, "propose_memory", {**MEMORY, "content": f"Python {index}"}
                )
            assert len(await core.personal.context(env.owner, "Python")) == 5
            with pytest.raises(AuthorizationError):
                await core.personal.memories(env.owner + 1)
            with pytest.raises(AuthorizationError):
                await core.personal.context(env.owner + 1, "Python")
            with pytest.raises(ValidationError):
                await pending.propose(
                    env.owner, "propose_memory", {**MEMORY, "content": "Python 0"}, turn="duplicate"
                )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "value", ["password is example", "Tôi có lẽ thích học", "cccd của tôi", "bệnh án của tôi"]
)
def test_sensitive_or_speculative_memory_rejected(value):
    with pytest.raises(ValidationError):
        memory_content(value, SecretFilter())


@pytest.mark.parametrize("value", ["25:00", "09:00:00", "9:00", "09:00+07:00", "a"])
def test_strict_local_clock(value):
    with pytest.raises(ValidationError):
        clock_time(value)


@pytest.mark.parametrize(
    "change", [dict(workdays=[]), dict(workdays=[True]), dict(end="08:00"), dict(break_minutes=-1)]
)
def test_work_validation(change):
    values = {**WORK, **change}
    with pytest.raises(ValidationError):
        work_config(
            values["workdays"],
            values["start"],
            values["end"],
            values["break_minutes"],
            values["memory_suggestions"],
        )


@pytest.mark.parametrize(
    "change", [dict(target="channel"), dict(fallback=True), dict(weekday=True), dict(enabled="yes")]
)
def test_routing_requires_explicit_valid_policy(change):
    with pytest.raises(ValidationError):
        PolicyData(kind="morning", **change)


def test_planner_requires_configuration_durations_and_approval_keeps_links(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            a = await core.tasks.create(
                env.owner,
                TaskData(title="First", estimated_minutes=45, priority="high"),
                request_id="a",
            )
            await core.tasks.create(env.owner, TaskData(title="No duration"), request_id="b")
            initial = await core.planner.draft(env.owner, NOW.date().isoformat())
            assert not initial["entries"] and len(initial["unscheduled"]) == 2
            await approve(env, pending, "configure_work", WORK)
            old = await core.calendar.create(
                env.owner,
                EventData(
                    title="Already confirmed",
                    starts_at=NOW + timedelta(hours=1),
                    ends_at=NOW + timedelta(hours=2),
                ),
                request_id="e",
            )
            draft = await core.planner.draft(env.owner, NOW.date().isoformat())
            assert len(draft["entries"]) == 1 and draft["entries"][0]["task_id"] == a.id
            assert (
                len(draft["unscheduled"]) == 1 and "thời lượng" in draft["unscheduled"][0]["reason"]
            )
            args = dict(
                date=draft["date"],
                days=1,
                entries=[
                    {k: e[k] for k in ("task_id", "starts_at", "ends_at")} for e in draft["entries"]
                ],
            )
            proposal = await pending.propose(env.owner, "propose_schedule_tasks", args, turn="plan")
            async with env.database.sessions() as session:
                assert len(list(await session.scalars(select(CalendarEvent)))) == 1
            await bind(pending, env.owner, proposal)
            await pending.decide(env.owner, proposal["id"], "123", "456", choice="keep")
            async with env.database.sessions() as session:
                rows = list(await session.scalars(select(CalendarEvent)))
                assert len(rows) == 2
                assert [r for r in rows if r.task_id == a.id][0].status == "confirmed"
                existing = await session.get(CalendarEvent, old.id)
                assert existing.starts_at == old.starts_at and existing.ends_at == old.ends_at
            assert not (await core.planner.draft(env.owner, NOW.date().isoformat()))["entries"]

    asyncio.run(scenario())


def test_planner_honors_preferences_breaks_cap_and_stale_conflicts(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            await approve(env, pending, "configure_work", {**WORK, "end": "23:00"})
            for index in range(12):
                await core.tasks.create(
                    env.owner,
                    TaskData(title=f"Task {index}", estimated_minutes=10),
                    request_id=str(index),
                )
            draft = await core.planner.draft(
                env.owner, NOW.date().isoformat(), preferred_period="afternoon"
            )
            assert len(draft["entries"]) == 10 and len(draft["unscheduled"]) == 2
            from datetime import datetime

            starts = [datetime.fromisoformat(e["starts_at"]) for e in draft["entries"]]
            assert starts[0].astimezone(zone("Asia/Ho_Chi_Minh")).hour == 12
            assert all(
                b - a >= timedelta(minutes=20) for a, b in zip(starts, starts[1:], strict=False)
            )
            args = dict(
                date=draft["date"],
                days=1,
                entries=[
                    {k: e[k] for k in ("task_id", "starts_at", "ends_at")} for e in draft["entries"]
                ],
            )
            p = await pending.propose(env.owner, "propose_schedule_tasks", args, turn="plan")
            await bind(pending, env.owner, p)
            await core.calendar.create(
                env.owner,
                EventData(
                    title="New conflict",
                    starts_at=starts[0],
                    ends_at=starts[0] + timedelta(minutes=5),
                ),
                request_id="conflict",
            )
            with pytest.raises(ValidationError):
                await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            async with env.database.sessions() as session:
                assert len(list(await session.scalars(select(CalendarEvent)))) == 1

    asyncio.run(scenario())


def test_planner_failed_commit_is_atomic(core_factory, monkeypatch):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            await approve(env, pending, "configure_work", WORK)
            for index in range(2):
                await core.tasks.create(
                    env.owner,
                    TaskData(title=f"T{index}", estimated_minutes=20),
                    request_id=str(index),
                )
            draft = await core.planner.draft(env.owner, NOW.date().isoformat())
            args = dict(
                date=draft["date"],
                days=1,
                entries=[
                    {k: e[k] for k in ("task_id", "starts_at", "ends_at")} for e in draft["entries"]
                ],
            )
            p = await pending.propose(env.owner, "propose_schedule_tasks", args, turn="plan")
            await bind(pending, env.owner, p)
            flush = Session.flush

            def fail(session, *a, **kw):
                if any(isinstance(r, CalendarEvent) for r in session.new):
                    raise OperationalError("synthetic", {}, RuntimeError())
                return flush(session, *a, **kw)

            with monkeypatch.context() as patch:
                patch.setattr(Session, "flush", fail)
                with pytest.raises(StorageError):
                    await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            async with env.database.sessions() as session:
                assert not list(await session.scalars(select(CalendarEvent)))
            assert (await pending.get(env.owner, p["id"]))["status"] == "pending"

    asyncio.run(scenario())


def test_agent_memory_is_separate_from_primary_action_and_never_preconfirmed(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, gateway, usage = personal_bundle(env)
            transport = SimpleNamespace(
                respond=AsyncMock(
                    return_value=response(("create_task", TASK_ARGS), ("propose_memory", MEMORY))
                )
            )
            agent = AgentOrchestrator(
                CONFIG,
                env.tasks.authorization,
                gateway,
                pending,
                usage,
                transport,
                clock=lambda: NOW,
            )
            result = await agent.turn(
                env.owner, "111", "Tạo task Synthetic task. Tôi thích học Python vào buổi sáng"
            )
            assert result["pending"]["action"] == "create_task"
            assert result["memory_suggestion"]["action"] == "propose_memory"
            assert result["memory_suggestion"]["preview"]["source"] == "dm:111"
            assert (await core.personal.memories(env.owner))["total"] == 0
            assert (await core.tasks.list(env.owner)).total == 0
            await bind(pending, env.owner, result["memory_suggestion"])
            await pending.decide(
                env.owner, result["memory_suggestion"]["id"], "123", "456", choice="keep"
            )
            assert (await core.tasks.list(env.owner)).total == 0
            agent.close()

    asyncio.run(scenario())


def test_agent_uses_only_relevant_confirmed_memory_and_revokes_inflight_result(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, gateway, usage = personal_bundle(env)
            await approve(env, pending, "propose_memory", MEMORY)
            transport = SimpleNamespace(
                respond=AsyncMock(return_value=response(text="Bạn thích học Python buổi sáng?"))
            )
            agent = AgentOrchestrator(
                CONFIG,
                env.tasks.authorization,
                gateway,
                pending,
                usage,
                transport,
                clock=lambda: NOW,
            )
            await agent.turn(env.owner, "context", "Tôi học Python lúc nào?")
            sent = transport.respond.await_args.kwargs
            assert MEMORY["content"] in encode(sent["inputs"])
            assert MEMORY["content"] not in sent["instructions"]

            async def revoke(**kwargs):
                agent.clear(env.owner)
                return response(text="Old memory")

            transport.respond.side_effect = revoke
            with pytest.raises(ValidationError, match="đã thay đổi"):
                await agent.turn(env.owner, "revoked", "Python?")
            assert not agent.context
            agent.close()

    asyncio.run(scenario())


def test_personal_ai_failure_uses_facts_and_background_quota(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, _, _, usage = personal_bundle(env)
            fake = SimpleNamespace(respond=AsyncMock(side_effect=TimeoutError()))
            ai = PersonalAI(CONFIG, env.tasks.authorization, core.personal, usage, fake)
            assert (await ai.preference(env.owner, dict(entries=[]), background=True))[
                "period"
            ] is None
            with pytest.raises(AuthorizationError):
                await ai.preference(env.owner + 1, {}, background=True)

    asyncio.run(scenario())


def test_only_one_memory_candidate_and_toggle_disables_suggestions(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, gateway, usage = personal_bundle(env)
            fake = SimpleNamespace(
                respond=AsyncMock(
                    side_effect=[
                        response(
                            ("propose_memory", MEMORY),
                            ("propose_memory", {**MEMORY, "content": "Python"}),
                        ),
                        response(text="Bạn muốn tra cứu Python hay lập kế hoạch?"),
                    ]
                )
            )
            agent = AgentOrchestrator(
                CONFIG, env.tasks.authorization, gateway, pending, usage, fake, clock=lambda: NOW
            )
            answer = await agent.turn(env.owner, "one", MEMORY["content"])
            assert answer["memory_suggestion"]
            async with env.database.sessions() as session:
                rows = list(await session.scalars(select(PendingAction)))
                assert len(rows) == 1
            await approve(env, pending, "configure_work", {**WORK, "memory_suggestions": False})
            fake.respond.side_effect = None
            fake.respond.return_value = response(text="Bạn muốn học Python thế nào?")
            await agent.turn(env.owner, "off", MEMORY["content"])
            assert "propose_memory" not in {
                t["name"] for t in fake.respond.await_args.kwargs["tools"]
            }
            agent.close()

    asyncio.run(scenario())


def test_deleting_edited_memory_erases_old_unapproved_candidate_copies(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            older = await pending.propose(env.owner, "propose_memory", MEMORY, turn="older")
            key = (await approve(env, pending, "propose_memory", MEMORY))["ids"][0]
            await approve(
                env,
                pending,
                "update_memory",
                dict(
                    memory_id=key,
                    expected_version=1,
                    **{**MEMORY, "content": "Tôi thích học Python buổi tối"},
                ),
            )
            await approve(env, pending, "delete_memory", dict(memory_id=key, expected_version=2))
            old = await pending.get(env.owner, older["id"])
            assert old["preview"] == {"erased": True} and old["status"] == "rejected"
            assert (await core.personal.memories(env.owner))["total"] == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("date_value", ["2030-03-10", "2030-11-03"])
def test_planner_dst_gap_or_fold_work_start_is_not_guessed(core_factory, date_value):
    async def scenario():
        from datetime import UTC, datetime

        from app.db.models import User

        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            async with env.database.sessions.begin() as session:
                (await session.get(User, str(env.owner))).timezone = "America/New_York"
            current = datetime.fromisoformat(date_value).replace(tzinfo=UTC) - timedelta(days=1)
            core.personal.clock = pending.clock = lambda: current
            await approve(
                env,
                pending,
                "configure_work",
                {**WORK, "start": "02:30" if "03-" in date_value else "01:30", "end": "04:00"},
            )
            await core.tasks.create(
                env.owner, TaskData(title="DST", estimated_minutes=30), request_id="dst"
            )
            assert not (await core.planner.draft(env.owner, date_value))["entries"]

    asyncio.run(scenario())
