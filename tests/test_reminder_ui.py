import asyncio
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest

from app.discord_bot.client import NovaClient
from app.discord_bot.views.reminders import (
    ConfirmationView,
    DateView,
    DetailView,
    DraftView,
    ListView,
    NotificationButton,
    ReminderDraft,
    ReminderModal,
)
from app.domain.core import TaskData
from app.domain.modules import Screen
from app.scheduler.dispatcher import ReminderDispatcher

START = datetime(2026, 10, 25, 13, tzinfo=UTC)


@pytest.fixture
def reminder_ui(core_ui_factory):
    @asynccontextmanager
    async def factory():
        async with core_ui_factory() as (env, dashboard):
            service = dashboard.reminders.service
            clock = [START - timedelta(minutes=1)]
            service.clock = lambda: clock[0]
            service.approvals.clock = service.clock
            service.channel_validator = AsyncMock()
            sender = SimpleNamespace(
                send=AsyncMock(return_value="123456789"), available=lambda: True
            )
            yield SimpleNamespace(
                **vars(env),
                dashboard=dashboard,
                controller=dashboard.reminders,
                service=service,
                clock=clock,
                sender=sender,
                dispatcher=ReminderDispatcher(service, sender),
            )

    return factory


def current(interaction):
    return interaction.edit_original_response.await_args.kwargs["view"]


async def press(interaction, view, action, value=None):
    interaction.response.is_done.return_value = False
    button = next(
        child
        for child in view.children
        if getattr(child, "action", None) == action
        and (value is None or getattr(child, "value", None) == value)
    )
    await button.callback(interaction)


async def choose(interaction, view, action, value):
    interaction.response.is_done.return_value = False
    select = next(child for child in view.children if getattr(child, "action", None) == action)
    select._values = [value]
    await select.callback(interaction)


async def start_draft(env, interaction, *, title="Test reminder", exact=""):
    await env.dashboard.navigate(interaction, Screen.REMINDERS, new_panel=True)
    assert isinstance(current(interaction), ListView)
    await press(interaction, current(interaction), "create")
    modal = interaction.response.send_modal.await_args.args[0]
    modal.title_input._value, modal.time_input._value = title, exact
    interaction.response.is_done.return_value = False
    await modal.on_submit(interaction)
    assert isinstance(current(interaction), DraftView)
    return current(interaction)


async def save_exact(env, interaction, *, title="Test reminder"):
    await start_draft(env, interaction, title=title, exact="2026-10-25 20:00")
    await press(interaction, current(interaction), "save")
    assert isinstance(current(interaction), DetailView)
    return current(interaction).state["record"]


def test_entire_create_picker_weekly_and_links_flow_only_saves_when_owner_clicks_save(
    reminder_ui, interaction
):
    async def scenario():
        async with reminder_ui() as env:
            task = await env.tasks.create(env.owner, TaskData(title="Linked task"), request_id="t")
            await start_draft(env, interaction)
            assert (await env.service.list(env.owner)).total == 0
            await press(interaction, current(interaction), "date")
            assert isinstance(current(interaction), DateView)
            await choose(interaction, current(interaction), "hour", "20")
            await choose(interaction, current(interaction), "minute", "0")
            await press(interaction, current(interaction), "date_apply")
            await choose(interaction, current(interaction), "recurrence", "weekly")
            await choose(interaction, current(interaction), "weekday", "6")
            await press(interaction, current(interaction), "links", "task_id")
            await choose(interaction, current(interaction), "link", task.id)
            assert (await env.service.list(env.owner)).total == 0
            await press(interaction, current(interaction), "save")
            row = current(interaction).state["record"]
            assert (
                row.next_fire_at == START and row.recurrence.weekday == 6 and row.task_id == task.id
            )
            interaction.message.edit.assert_not_awaited()
            assert (
                "Đã lưu"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )

    asyncio.run(scenario())


def test_edit_cancel_pause_resume_require_explicit_confirmation_and_can_be_rejected(
    reminder_ui, interaction
):
    async def scenario():
        async with reminder_ui() as env:
            row = await save_exact(env, interaction)
            await press(interaction, current(interaction), "edit")
            modal = interaction.response.send_modal.await_args.args[0]
            modal.title_input._value = "Edited"
            modal.time_input._value = modal.original_time
            interaction.response.is_done.return_value = False
            await modal.on_submit(interaction)
            await press(interaction, current(interaction), "save")
            assert isinstance(current(interaction), ConfirmationView)
            assert (await env.service.get(env.owner, row.id)).title == row.title
            await press(interaction, current(interaction), "approve")
            assert (await env.service.get(env.owner, row.id)).title == "Edited"
            await press(interaction, current(interaction), "status", "paused")
            await press(interaction, current(interaction), "approve")
            assert (await env.service.get(env.owner, row.id)).status == "paused"
            await press(interaction, current(interaction), "status", "active")
            await press(interaction, current(interaction), "approve")
            assert (await env.service.get(env.owner, row.id)).status == "active"
            await press(interaction, current(interaction), "status", "cancelled")
            await press(interaction, current(interaction), "reject")
            assert (await env.service.get(env.owner, row.id)).status == "active"

    asyncio.run(scenario())


def test_missing_time_bad_time_and_stale_modal_do_not_save_and_keep_inputs(
    reminder_ui, interaction
):
    async def scenario():
        async with reminder_ui() as env:
            await start_draft(env, interaction, title="Keep title", exact="2026-10-25 25:00")
            assert current(interaction).state["draft"].title == "Keep title"
            await press(interaction, current(interaction), "text")
            modal = interaction.response.send_modal.await_args.args[0]
            assert modal.time_input.default == "2026-10-25 25:00"
            modal.expires_at = monotonic() - 1
            modal.time_input._value = "2026-10-25 20:00"
            await modal.on_submit(interaction)
            assert (await env.service.list(env.owner)).total == 0
            await press(interaction, current(interaction), "save")
            assert (await env.service.list(env.owner)).total == 0

    asyncio.run(scenario())


def test_settings_dm_and_quiet_hours_are_real_but_never_change_before_approve(
    reminder_ui, interaction
):
    async def scenario():
        async with reminder_ui() as env:
            await env.controller.open(interaction)
            await press(interaction, current(interaction), "settings")
            await press(interaction, current(interaction), "dm")
            assert (await env.service.preferences(env.owner)).dm_enabled
            await press(interaction, current(interaction), "approve")
            assert not (await env.service.preferences(env.owner)).dm_enabled
            await press(interaction, current(interaction), "quiet")
            modal = interaction.response.send_modal.await_args.args[0]
            modal.start._value, modal.end._value = "22:00", "06:00"
            interaction.response.is_done.return_value = False
            await modal.on_submit(interaction)
            assert (await env.service.preferences(env.owner)).quiet_start is None
            await press(interaction, current(interaction), "approve")
            assert (await env.service.preferences(env.owner)).quiet_start.hour == 22

    asyncio.run(scenario())


def test_notification_dynamic_callback_after_restart_is_owner_and_message_bound(
    reminder_ui, interaction
):
    async def scenario():
        async with reminder_ui() as env:
            row = await save_exact(env, interaction)
            env.clock[0] = START
            await env.dispatcher.tick()
            delivery = (await env.service.history(env.owner, row.id))[0]
            button = NotificationButton("snooze", delivery.id)
            match = re.fullmatch(
                r"nova:reminder:v1:(?P<action>done|snooze|cancel):(?P<delivery>[0-9a-f-]{36})",
                button.item.custom_id,
            )
            restored = await NotificationButton.from_custom_id(interaction, button.item, match)
            interaction.client = SimpleNamespace(dashboard=env.dashboard)
            interaction.message.id = 123456789
            interaction.user.id += 1
            await restored.callback(interaction)
            assert len(await env.service.history(env.owner, row.id)) == 1
            interaction.user.id -= 1
            interaction.response.is_done.return_value = False
            await restored.callback(interaction)
            assert len(await env.service.history(env.owner, row.id)) == 2
            interaction.response.is_done.return_value = False
            await restored.callback(interaction)
            assert len(await env.service.history(env.owner, row.id)) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("entry", ["button", "select", "modal", "open", "notification"])
def test_reminder_ui_entrypoints_deny_non_owner(reminder_ui, interaction, entry):
    async def scenario():
        async with reminder_ui() as env:
            await env.controller.open(interaction)
            view = current(interaction)
            interaction.user.id += 1
            interaction.response.is_done.return_value = False
            with patch.object(env.service, "get", new=AsyncMock()) as read:
                if entry == "button":
                    await press(interaction, view, "create")
                elif entry == "select":
                    await choose(interaction, view, "filter", "active")
                elif entry == "modal":
                    modal = ReminderModal(
                        env.controller,
                        view,
                        ReminderDraft(timezone="UTC"),
                    )
                    await modal.on_submit(interaction)
                elif entry == "open":
                    await env.controller.open(interaction, key="fake")
                else:
                    await env.controller.notification(interaction, "fake", "done")
                read.assert_not_awaited()

    asyncio.run(scenario())


def test_runtime_registers_dynamic_buttons_and_worker_starts_once_stops_before_db_close(settings):
    async def scenario():
        from app.db.session import Database

        database = Database(settings.database_url)
        client = NovaClient(settings, database)
        try:
            with patch.object(client.tree, "sync", new=AsyncMock(return_value=[])):
                await client.setup_hook()
            assert NotificationButton in client._connection._view_store._dynamic_items.values()
            with patch.object(client, "is_ready", return_value=True):
                client.reminder_sender.available = lambda: False
                await client.on_ready()
                first = client.reminder_dispatcher.task
                await client.on_ready()
                assert client.reminder_dispatcher.task is first
                await client.close()
                assert first.done() and client.reminder_dispatcher.task is None
        finally:
            await client.close()

    asyncio.run(scenario())


def test_lists_paging_filter_back_and_home_do_not_overwrite_anchor(reminder_ui, interaction):
    async def scenario():
        from app.domain.reminders import ReminderData

        async with reminder_ui() as env:
            for index in range(7):
                await env.service.create(
                    env.owner,
                    ReminderData(title=f"R {index}", next_fire_at=START),
                    request_id=str(index),
                )
            await env.controller.open(interaction)
            await press(interaction, current(interaction), "page", 1)
            assert current(interaction).state["page"] == 1
            await choose(interaction, current(interaction), "filter", "paused")
            assert (
                "Chưa có"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            await press(interaction, current(interaction), "home")
            interaction.message.edit.assert_not_awaited()
            assert (
                "PERSONAL CONTROL CENTER"
                in interaction.edit_original_response.await_args.kwargs["embed"].title
            )

    asyncio.run(scenario())


def test_expired_and_replaced_draft_cannot_save_and_ttl_does_not_extend(reminder_ui, interaction):
    async def scenario():
        async with reminder_ui() as env:
            original = await start_draft(env, interaction, exact="2026-10-25 20:00")
            deadline = original.state["draft"].expires_at
            await choose(interaction, original, "recurrence", "daily")
            assert current(interaction).state["draft"].expires_at == deadline
            await press(interaction, original, "save")  # This view has already been replaced.
            assert (await env.service.list(env.owner)).total == 0
            current(interaction).expires_at = monotonic() - 1
            await press(interaction, current(interaction), "save")
            assert (await env.service.list(env.owner)).total == 0

    asyncio.run(scenario())


def test_discord_render_error_after_commit_never_resubmits_create(reminder_ui, interaction):
    async def scenario():
        async with reminder_ui() as env:
            await start_draft(env, interaction, exact="2026-10-25 20:00")
            error = discord.HTTPException(
                SimpleNamespace(status=500, reason="Error"), "private response"
            )
            with patch.object(env.controller, "open", new=AsyncMock(side_effect=error)):
                await press(interaction, current(interaction), "save")
            assert (
                "đã lưu"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            await press(interaction, current(interaction), "save")
            assert (await env.service.list(env.owner)).total == 1

    asyncio.run(scenario())


def test_notification_cancel_requires_confirm_after_restart_and_limits_components(
    reminder_ui, interaction
):
    async def scenario():
        async with reminder_ui() as env:
            row = await save_exact(env, interaction)
            env.clock[0] = START
            await env.dispatcher.tick()
            delivery = (await env.service.history(env.owner, row.id))[0]
            interaction.message.id = 123456789
            interaction.response.is_done.return_value = False
            await env.controller.notification(interaction, delivery.id, "cancel")
            assert isinstance(current(interaction), ConfirmationView)
            assert (await env.service.get(env.owner, row.id)).status == "done"
            await press(interaction, current(interaction), "approve")
            assert (await env.service.get(env.owner, row.id)).status == "cancelled"
            view = current(interaction)
            assert len(view.children) <= 25
            assert len({child.custom_id for child in view.children}) == len(view.children)
            embed = interaction.edit_original_response.await_args.kwargs["embed"]
            assert len(embed) < 6000
            assert all(len(field.value) <= 1024 for field in embed.fields)

    asyncio.run(scenario())
