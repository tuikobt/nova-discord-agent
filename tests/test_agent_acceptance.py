import asyncio
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_agent import CONFIG, NOW, TASK_ARGS, bind, bundle, response

from app.agent.client import ResponsesClient
from app.agent.config import AgentConfig
from app.agent.orchestrator import AgentOrchestrator
from app.db.models import ReminderDelivery, Task
from app.db.session import Database
from app.discord_bot.agent_controller import AgentButton
from app.discord_bot.client import NovaClient
from app.domain.core import EventData, TaskData
from app.domain.errors import StorageError, ValidationError
from app.domain.reminders import ReminderData
from app.scheduler.dispatcher import ReminderDispatcher


def test_dm_to_preview_restart_approve_database_receipt(settings, authorization, interaction):
    async def scenario():
        transport = SimpleNamespace(
            respond=AsyncMock(return_value=response(("create_task", TASK_ARGS))), close=AsyncMock()
        )
        with patch("app.discord_bot.agent_controller.ResponsesClient", return_value=transport):
            database = Database(settings.database_url)
            client = NovaClient(replace(settings, ai=CONFIG), database)
            await database.initialize()
            await client.settings_service.initialize_owner(settings.owner_id, settings.timezone)
            sent = SimpleNamespace(id=456, channel=SimpleNamespace(id=123), edit=AsyncMock())
            message = SimpleNamespace(
                id=111,
                author=SimpleNamespace(id=settings.owner_id, bot=False),
                guild=None,
                content="Tạo task Synthetic task",
                channel=SimpleNamespace(send=AsyncMock(return_value=sent)),
            )
            await client.on_message(message)
            proposal = await client.agent.pending.existing(settings.owner_id, "111")
            assert proposal["message_id"] == "456"
            assert (await client.core_services.tasks.list(settings.owner_id)).total == 0
            await client.close()
            second_database = Database(settings.database_url)
            restarted = NovaClient(replace(settings, ai=CONFIG), second_database)
            try:
                interaction.guild = None
                interaction.channel_id = 123
                interaction.message.id = 456
                interaction.client = restarted
                button = AgentButton("keep", proposal["id"])
                await button.callback(interaction)
                rows = await restarted.core_services.tasks.list(settings.owner_id)
                assert rows.total == 1 and rows.items[0].title == TASK_ARGS["title"]
                assert "Đã lưu" in interaction.edit_original_response.await_args.kwargs["content"]
                await button.callback(interaction)
                assert (await restarted.core_services.tasks.list(settings.owner_id)).total == 1
            finally:
                await restarted.close()

    asyncio.run(scenario())


def test_transaction_commit_failure_rolls_back_task_audit_and_receipt(core_factory, monkeypatch):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = bundle(env)
            p = await pending.propose(env.owner, "create_task", TASK_ARGS, turn="one")
            await bind(pending, env.owner, p)
            original_flush = Session.flush

            def fail_mutation(session, *args, **kwargs):
                if any(isinstance(row, Task) for row in session.new):
                    raise OperationalError("synthetic", {}, RuntimeError())
                return original_flush(session, *args, **kwargs)

            with monkeypatch.context() as patcher:
                patcher.setattr(Session, "flush", fail_mutation)
                with pytest.raises(StorageError):
                    await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            assert (await core.tasks.list(env.owner)).total == 0
            assert (await pending.get(env.owner, p["id"]))["status"] == "pending"
            await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            assert (await core.tasks.list(env.owner)).total == 1

    asyncio.run(scenario())


def test_claimed_reminder_prevents_reschedule(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = bundle(env)
            core.reminders.clock = lambda: NOW
            event = await core.calendar.create(
                env.owner,
                EventData(
                    title="Event",
                    starts_at=NOW + timedelta(hours=1),
                    ends_at=NOW + timedelta(hours=2),
                ),
                request_id="e",
            )
            reminder = await core.reminders.create(
                env.owner,
                ReminderData(
                    title="R", event_id=event.id, next_fire_at=NOW + timedelta(minutes=55)
                ),
                request_id="r",
            )
            args = dict(
                changes=[
                    dict(
                        event_id=event.id,
                        starts_at=(NOW + timedelta(hours=3)).isoformat(),
                        ends_at=(NOW + timedelta(hours=4)).isoformat(),
                    )
                ]
            )
            p = await pending.propose(env.owner, "propose_reschedule", args, turn="move")
            await bind(pending, env.owner, p)
            async with env.database.sessions.begin() as session:
                session.add(
                    ReminderDelivery(
                        reminder_id=reminder.id,
                        scheduled_fire_at=reminder.next_fire_at,
                        status="claimed",
                        claimed_at=NOW,
                    )
                )
            with pytest.raises(ValidationError, match="đang gửi"):
                await pending.decide(env.owner, p["id"], "123", "456", choice="shift")
            assert (await core.calendar.get(env.owner, event.id)).starts_at == event.starts_at

    asyncio.run(scenario())


def test_context_expires_and_can_be_cleared_without_deleting_tasks(core_factory):
    async def scenario():
        async with core_factory() as env:
            _, pending, gateway, usage = bundle(env)
            clock = [NOW]
            agent = AgentOrchestrator(
                CONFIG,
                env.tasks.authorization,
                gateway,
                pending,
                usage,
                SimpleNamespace(respond=AsyncMock(return_value=response(text="Bạn muốn làm gì?"))),
                clock=lambda: clock[0],
            )
            await agent.turn(env.owner, "1", "Chào NOVA")
            assert len(agent.context) == 2
            assert agent.expiry_timer is not None
            clock[0] += timedelta(minutes=31)
            agent.expire()
            assert not agent.context
            await agent.turn(env.owner, "2", "Chào NOVA")
            agent.clear(env.owner)
            assert not agent.context and agent.expiry_timer is None
            agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "tool,args",
    [
        ("list_tasks", dict(status=None, project_id=None, due_from=None, due_to=None, limit=10)),
        ("list_projects", dict(status=None)),
        ("list_reminders", dict(status=None)),
        ("list_events", dict(date_from="2030-01-10", date_to="2030-01-10")),
        ("find_free_slots", dict(date="2030-01-10", min_minutes=30)),
        ("get_preferences", dict(keys=["timezone", "locale", "quiet_start"])),
        ("suggest_next_action", dict(date="2030-01-10")),
    ],
)
def test_read_tools_operate_on_real_sqlite_without_mutations(core_factory, tool, args):
    async def scenario():
        async with core_factory() as env:
            core, pending, gateway, _ = bundle(env)
            await core.tasks.create(env.owner, TaskData(title="Synthetic"), request_id="task")
            result = await gateway.call(env.owner, tool, args, turn="read", allowed={tool})
            assert result is not None
            assert (await core.tasks.list(env.owner)).total == 1
            assert await pending.existing(env.owner, "read") is None

    asyncio.run(scenario())


def test_sdk_parameters_and_no_network_constructor():
    async def scenario():
        sdk = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()), close=AsyncMock())
        with patch("app.agent.client.AsyncOpenAI", return_value=sdk) as constructor:
            client = ResponsesClient(CONFIG)
            await client.respond(
                inputs=[dict(role="user", content="synthetic")], instructions="safe", tools=[]
            )
            kwargs = sdk.responses.create.await_args.kwargs
            assert kwargs["store"] is False
            assert kwargs["parallel_tool_calls"] is False
            assert kwargs["model"] == CONFIG.model
            assert constructor.call_args.kwargs["max_retries"] == 0
            assert constructor.call_args.kwargs["base_url"] == "https://api.openai.com/v1"
            await client.close()
            sdk.close.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"AI_ENABLED": "true"},
        {"AI_ENABLED": "true", "AI_DAILY_TOKEN_LIMIT": "invalid"},
        {"AI_DAILY_TOKEN_LIMIT": "-1"},
    ],
)
def test_optional_ai_config_does_not_break_crud(values):
    config = AgentConfig.from_mapping(values)
    assert not config.ready
    assert "synthetic-key" not in repr(CONFIG)


def test_loop_limit_and_busy_turn_dont_mutate(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, gateway, usage = bundle(env)
            fake = SimpleNamespace(
                respond=AsyncMock(
                    side_effect=lambda **kwargs: response(("list_projects", dict(status=None)))
                )
            )
            agent = AgentOrchestrator(
                CONFIG, env.tasks.authorization, gateway, pending, usage, fake
            )
            async with agent.lock:
                result = await agent.turn(env.owner, "busy", "Có việc gì?")
                assert "lượt trước" in result["text"]
            with pytest.raises(ValidationError, match="giới hạn"):
                await agent.turn(env.owner, "loop", "Có việc gì?")
            assert fake.respond.await_count == 4
            assert (await core.tasks.list(env.owner)).total == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("recurrence", ["none", "daily", "weekly"])
def test_agent_reminder_approval_reaches_existing_dispatcher(core_factory, recurrence):
    async def scenario():
        async with core_factory() as env:
            core, pending, gateway, _ = bundle(env)
            clock = [NOW]
            core.reminders.clock = lambda: clock[0]
            fire = NOW + timedelta(minutes=5)
            result = await gateway.call(
                env.owner,
                "create_reminder",
                dict(
                    title="Synthetic reminder",
                    first_fire_at=fire.isoformat(),
                    recurrence_type=recurrence,
                    task_id=None,
                    event_id=None,
                ),
                turn="reminder",
                allowed={"create_reminder"},
            )
            p = result["pending"]
            assert (await core.reminders.list(env.owner)).total == 0
            await bind(pending, env.owner, p)
            receipt = await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            key = receipt["ids"][0]
            sender = SimpleNamespace(send=AsyncMock(return_value="777"))
            clock[0] = fire
            worker = ReminderDispatcher(core.reminders, sender)
            await worker.tick()
            await worker.tick()
            sender.send.assert_awaited_once()
            reminder = await core.reminders.get(env.owner, key)
            assert reminder.status == ("done" if recurrence == "none" else "active")
            if recurrence != "none":
                assert reminder.next_fire_at > fire

    asyncio.run(scenario())


def test_clarification_continues_into_reminder_preview(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, gateway, usage = bundle(env)
            core.reminders.clock = lambda: NOW
            args = dict(
                title="Làm bài",
                first_fire_at=(NOW + timedelta(days=1, hours=8)).isoformat(),
                recurrence_type="none",
                task_id=None,
                event_id=None,
            )
            fake = SimpleNamespace(
                respond=AsyncMock(return_value=response(("create_reminder", args)))
            )
            agent = AgentOrchestrator(
                CONFIG, env.tasks.authorization, gateway, pending, usage, fake, clock=lambda: NOW
            )
            first = await agent.turn(env.owner, "1", "Mai nhắc tôi làm bài")
            assert "mấy giờ" in first["text"]
            second = await agent.turn(env.owner, "2", "18h")
            assert second["pending"]["status"] == "pending"
            assert (await core.reminders.list(env.owner)).total == 0
            agent.close()

    asyncio.run(scenario())


def test_owner_guard_rejects_content_access_even_when_ai_enabled(settings):
    class ForbiddenContent:
        @property
        def content(self):
            raise AssertionError("Unauthorized content was inspected")

    async def scenario():
        with patch(
            "app.discord_bot.agent_controller.ResponsesClient",
            return_value=SimpleNamespace(close=AsyncMock()),
        ):
            database = Database(settings.database_url)
            client = NovaClient(replace(settings, ai=CONFIG), database)
            try:
                message = ForbiddenContent()
                message.author = SimpleNamespace(id=settings.owner_id + 1, bot=False)
                message.guild = None
                await client.on_message(message)
            finally:
                await client.close()

    asyncio.run(scenario())
