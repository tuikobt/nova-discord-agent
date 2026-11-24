import asyncio
from dataclasses import replace
from datetime import time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest
from sqlalchemy import select
from test_agent import CONFIG, NOW
from test_personal import approve, personal_bundle

from app.db.models import AutomationRun, Task, User, UserSettings
from app.discord_bot.personal_controller import report_text
from app.discord_bot.report_sender import DiscordReportSender
from app.domain.authorization import AuthorizationError
from app.domain.core import EventData, TaskData
from app.domain.errors import ValidationError
from app.domain.reminder_delivery import DeliveryFailure
from app.services.automation_service import AutomationService


async def enable(env, core, pending, kind="morning", **kwargs):
    await approve(
        env,
        pending,
        "configure_automation",
        dict(
            kind=kind,
            enabled=True,
            time="10:01",
            weekday=NOW.weekday(),
            target="dm",
            channel_id=None,
            fallback=False,
            **kwargs,
        ),
    )
    core.personal.clock = lambda: NOW + timedelta(minutes=2)


async def current_run(env, kind="morning"):
    async with env.database.sessions() as session:
        return await session.scalar(
            select(AutomationRun).where(
                AutomationRun.kind == kind, AutomationRun.period_key == NOW.date().isoformat()
            )
        )


def test_automations_opt_in_idempotent_sent_metadata_and_restart(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            sender = SimpleNamespace(send=AsyncMock(return_value=("1", "2")))
            await core.automation.tick(sender)
            sender.send.assert_not_awaited()
            assert not any(
                p["enabled"] for p in (await core.personal.settings(env.owner))["policies"].values()
            )
            await enable(env, core, pending)
            await asyncio.gather(core.automation.tick(sender), core.automation.tick(sender))
            sender.send.assert_awaited_once()
            row = await current_run(env)
            assert row.status == "sent" and row.attempt_count == 1
            assert row.discord_message_id == "1" and row.channel_id == "2"
            restarted = AutomationService(
                env.database.sessions, env.tasks.authorization, core.personal, core.reports
            )
            await restarted.tick(sender)
            sender.send.assert_awaited_once()

    asyncio.run(scenario())


def test_quiet_hours_delay_without_attempt_and_catchup_expiry(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            await enable(env, core, pending)
            async with env.database.sessions.begin() as session:
                settings = await session.get(UserSettings, str(env.owner))
                settings.quiet_start, settings.quiet_end = time(10), time(11)
            sender = SimpleNamespace(send=AsyncMock(return_value=("1", "2")))
            await core.automation.tick(sender)
            sender.send.assert_not_awaited()
            assert (await current_run(env)).attempt_count == 0
            core.personal.clock = lambda: NOW + timedelta(hours=1, minutes=1)
            await core.automation.tick(sender)
            sender.send.assert_awaited_once()
            # Tomorrow's missed report is not sent beyond its two-hour window.
            core.personal.clock = lambda: NOW + timedelta(days=1, hours=3)
            await core.automation.tick(sender)
            sender.send.assert_awaited_once()
            history = await core.reports.history(env.owner)
            assert any(r["error"] == "overdue" for r in history["items"])

    asyncio.run(scenario())


def test_lease_retry_fencing_and_exhaustion(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            await enable(env, core, pending)
            await core.automation.enqueue(env.owner)
            key = (await current_run(env)).id
            first = await core.automation.claim(env.owner, key)
            assert first and not await core.automation.claim(env.owner, key)
            core.personal.clock = lambda: NOW + timedelta(minutes=5)
            second = await core.automation.claim(env.owner, key)
            assert second["token"] != first["token"]
            await core.automation.finish(env.owner, first, message=("stale", "2"))
            assert (await current_run(env)).status == "claimed"
            await core.automation.finish(env.owner, second, error="http_error")
            assert not await core.automation.claim(env.owner, key)
            core.personal.clock = lambda: NOW + timedelta(minutes=10)
            third = await core.automation.claim(env.owner, key)
            assert third["attempt"] == 3
            assert not await core.automation.claim(env.owner, key)
            await core.automation.finish(env.owner, third, error="http_error")
            assert (await current_run(env)).status == "failed"
            assert not await core.automation.claim(env.owner, key)

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["disabled", "timezone", "quiet", "owner"])
def test_changed_configuration_blocks_send(core_factory, change):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            await enable(env, core, pending)
            await core.automation.enqueue(env.owner)
            claim = await core.automation.claim(env.owner, (await current_run(env)).id)
            if change == "disabled":
                policy = (await core.personal.settings(env.owner))["policies"]["morning"]
                await approve(
                    env,
                    pending,
                    "configure_automation",
                    {k: v for k, v in {**policy, "enabled": False}.items() if k != "version"},
                )
            elif change == "timezone":
                async with env.database.sessions.begin() as session:
                    (await session.get(User, str(env.owner))).timezone = "UTC"
            elif change == "quiet":
                async with env.database.sessions.begin() as session:
                    row = await session.get(UserSettings, str(env.owner))
                    row.quiet_start, row.quiet_end = time(9), time(12)
            else:
                with pytest.raises(AuthorizationError):
                    await core.automation.ready_to_send(env.owner + 1, claim)
                return
            assert await core.automation.ready_to_send(env.owner, claim) is None

    asyncio.run(scenario())


def test_reports_are_real_counts_and_content_retention_keeps_idempotency(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = personal_bundle(env)
            empty = await core.reports.build(env.owner, "daily")
            assert not any(empty["counts"].values())
            assert "Chưa có dữ liệu" in report_text(empty)
            task = await core.tasks.create(
                env.owner,
                TaskData(title="Recorded", estimated_minutes=30, due_at=NOW - timedelta(days=1)),
                request_id="t",
            )
            await core.calendar.create(
                env.owner,
                EventData(
                    title="Recorded event", starts_at=NOW, ends_at=NOW + timedelta(minutes=30)
                ),
                request_id="e",
            )
            data = await core.reports.build(env.owner, "daily")
            assert (
                data["counts"]["unfinished"]
                == data["counts"]["overdue"]
                == data["counts"]["events"]
                == 1
            )
            async with env.database.sessions.begin() as session:
                row = await session.get(Task, task.id)
                row.status, row.completed_at = "done", NOW - timedelta(minutes=1)
            assert (await core.reports.build(env.owner, "daily"))["counts"]["completed"] == 1
            await enable(env, core, pending)
            await core.automation.tick(SimpleNamespace(send=AsyncMock(return_value=("1", "2"))))
            key = (await current_run(env)).id
            core.personal.clock = lambda: NOW + timedelta(days=32)
            assert (await core.reports.get(env.owner, key))["payload"] is None
            await core.automation.enqueue(env.owner)
            async with env.database.sessions() as session:
                retained = await session.get(AutomationRun, key)
                assert retained.status == "sent" and retained.payload_json is None
                assert retained.discord_message_id == "1"

    asyncio.run(scenario())


def test_background_quota_cannot_consume_foreground_budget(core_factory):
    async def scenario():
        async with core_factory() as env:
            _, _, _, usage = personal_bundle(env)
            config = replace(CONFIG, daily_requests=5, daily_tokens=1000)
            await usage.reserve(env.owner, config, 100, purpose="background")
            with pytest.raises(ValidationError):
                await usage.reserve(env.owner, config, 100, purpose="background")
            await usage.reserve(env.owner, config, 500, purpose="dm")

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "fallback,dm_enabled,channel_ok,success",
    [
        (False, True, True, False),
        (True, True, True, True),
        (True, False, True, False),
        (True, True, False, False),
    ],
)
def test_report_sender_requires_explicit_fallback_and_fresh_private_acl(
    authorization, fallback, dm_enabled, channel_ok, success
):
    async def scenario():
        owner = SimpleNamespace(
            send=AsyncMock(
                side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "")
            )
        )
        channel = SimpleNamespace(
            send=AsyncMock(return_value=SimpleNamespace(id=1, channel=SimpleNamespace(id=2)))
        )
        private = SimpleNamespace(validate_channel=AsyncMock(return_value=channel))
        if not channel_ok:
            private.validate_channel.side_effect = ValidationError("Public channel")
        client = SimpleNamespace(authorization=authorization, get_user=Mock(return_value=owner))
        sender = DiscordReportSender(client, private)
        payload = dict(
            kind="daily",
            timezone="UTC",
            period_start="2030-01-10",
            period_end="2030-01-11",
            as_of=NOW.isoformat(),
            counts=dict(unfinished=0, overdue=0, completed=0, created=0, events=0),
            note="DB",
            tasks=[],
            events=[],
        )
        routing = dict(
            policy=dict(target="dm", fallback=fallback, channel_id="2"), dm_enabled=dm_enabled
        )
        if success:
            assert await sender.send(
                authorization.owner_id, "00000000-0000-0000-0000-000000000000", payload, routing
            ) == ("1", "2")
            private.validate_channel.assert_awaited_once()
            assert channel.send.await_args.kwargs["allowed_mentions"].everyone is False
        else:
            with pytest.raises(DeliveryFailure):
                await sender.send(
                    authorization.owner_id, "00000000-0000-0000-0000-000000000000", payload, routing
                )
            channel.send.assert_not_awaited()

    asyncio.run(scenario())
