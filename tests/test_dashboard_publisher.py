import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from app.db.session import Database
from app.discord_bot.client import NovaClient
from app.discord_bot.dashboard_publisher import DashboardPublishError
from app.discord_bot.renderers.dashboard import render_dashboard
from app.discord_bot.views.dashboard import DashboardView
from app.domain.authorization import AuthorizationError
from app.domain.schemas import DashboardLocation


def http_error(cls=discord.NotFound):
    status = 403 if cls is discord.Forbidden else 404
    return cls(SimpleNamespace(status=status, reason="test"), "private HTTP response")


async def history(messages):
    for message in messages:
        yield message


@pytest.fixture
def channel(discord_client):
    value = Mock(spec=discord.TextChannel)
    value.id = 234567890123456789
    value.guild = SimpleNamespace(default_role=object())
    value.permissions_for.return_value = SimpleNamespace(view_channel=False)
    value.history = Mock(side_effect=lambda **kwargs: history([]))
    message = SimpleNamespace(
        id=345678901234567890,
        channel=value,
        author=discord_client.user,
        embeds=[render_dashboard()],
        pinned=False,
        pin=AsyncMock(),
        edit=AsyncMock(),
        jump_url="https://discord.com/channels/123/234/345",
    )

    async def pinned(**kwargs):
        message.pinned = True

    message.pin.side_effect = pinned
    value.send = AsyncMock(return_value=message)
    value.fetch_message = AsyncMock(return_value=message)
    discord_client.get_channel.return_value = value
    return value


@pytest.fixture
def saved_settings(settings_mock):
    async def save(actor_id, location):
        settings_mock.get.return_value = replace(settings_mock.get.return_value, dashboard=location)

    settings_mock.save_dashboard.side_effect = save
    return settings_mock


def test_menu_creates_pins_and_saves_one_anchor_for_concurrent_requests(
    controller, channel, saved_settings
):
    async def scenario():
        actor = controller.authorization.owner_id
        view = DashboardView(controller)
        results = await asyncio.gather(
            *(controller.publisher.ensure(actor, channel, view) for _ in range(3))
        )
        channel.send.assert_awaited_once()
        channel.send.return_value.pin.assert_awaited_once()
        assert all(result.message.id == channel.send.return_value.id for result in results)
        assert saved_settings.get.return_value.dashboard == DashboardLocation(
            channel.id, channel.send.return_value.id
        )
        assert all(not result.pin_warning for result in results)

    asyncio.run(scenario())


def test_restart_uses_db_location_instead_of_creating_new_dashboard(
    controller, channel, saved_settings, interaction
):
    async def scenario():
        actor = interaction.user.id
        await controller.publisher.ensure(actor, channel, DashboardView(controller))
        # A new controller/publisher represents a restarted process; only DB data remains.
        restarted = type(controller)(
            controller.client, controller.authorization, saved_settings, controller.core.services
        )
        await restarted.restore()
        await restarted.publisher.ensure(actor, channel, DashboardView(restarted))
        channel.send.assert_awaited_once()
        controller.client.add_view.assert_called_once()
        assert (
            controller.client.add_view.call_args.kwargs["message_id"]
            == channel.send.return_value.id
        )

    asyncio.run(scenario())


def test_deleted_anchor_is_recreated_once(controller, channel, saved_settings):
    async def scenario():
        old_location = DashboardLocation(channel.id, channel.send.return_value.id - 1)
        saved_settings.get.return_value = replace(
            saved_settings.get.return_value, dashboard=old_location
        )
        channel.fetch_message.side_effect = http_error()
        await controller.publisher.ensure(
            controller.authorization.owner_id, channel, DashboardView(controller)
        )
        channel.send.assert_awaited_once()
        assert saved_settings.get.return_value.dashboard.message_id != old_location.message_id

    asyncio.run(scenario())


def test_deleted_channel_can_recover_in_current_private_channel(
    controller, channel, saved_settings, discord_client
):
    async def scenario():
        saved_settings.get.return_value = replace(
            saved_settings.get.return_value, dashboard=DashboardLocation(111, 222)
        )
        discord_client.get_channel.return_value = None
        discord_client.fetch_channel.side_effect = http_error()
        result = await controller.publisher.ensure(
            controller.authorization.owner_id, channel, DashboardView(controller)
        )
        assert result.message.channel.id == channel.id
        channel.send.assert_awaited_once()

    asyncio.run(scenario())


def test_forbidden_fetch_does_not_create_duplicate_or_replace_location(
    controller, channel, saved_settings
):
    async def scenario():
        original = DashboardLocation(channel.id, channel.send.return_value.id)
        saved_settings.get.return_value = replace(
            saved_settings.get.return_value, dashboard=original
        )
        channel.fetch_message.side_effect = http_error(discord.Forbidden)
        with pytest.raises(discord.Forbidden):
            await controller.publisher.ensure(
                controller.authorization.owner_id, channel, DashboardView(controller)
            )
        channel.send.assert_not_awaited()
        saved_settings.save_dashboard.assert_not_awaited()
        assert saved_settings.get.return_value.dashboard == original

    asyncio.run(scenario())


def test_menu_in_another_channel_reuses_existing_location(controller, channel, saved_settings):
    async def scenario():
        saved_settings.get.return_value = replace(
            saved_settings.get.return_value,
            dashboard=DashboardLocation(channel.id, channel.send.return_value.id),
        )
        other_channel = Mock(spec=discord.TextChannel)
        other_channel.send = AsyncMock()
        await controller.publisher.ensure(
            controller.authorization.owner_id, other_channel, DashboardView(controller)
        )
        other_channel.send.assert_not_awaited()
        channel.send.assert_not_awaited()
        assert saved_settings.get.return_value.dashboard.channel_id == channel.id

    asyncio.run(scenario())


def test_missing_pin_permission_preserves_anchor_and_warns(
    controller, channel, saved_settings, interaction
):
    async def scenario():
        channel.send.return_value.pin.side_effect = http_error(discord.Forbidden)
        interaction.guild_id = 123
        interaction.channel = channel
        await controller.menu(interaction)
        assert "chưa ghim" in interaction.edit_original_response.await_args.kwargs["content"]
        await controller.menu(interaction)
        channel.send.assert_awaited_once()
        assert saved_settings.get.return_value.dashboard is not None

    asyncio.run(scenario())


def test_history_reconciles_interrupted_send_without_new_message(
    controller, channel, saved_settings
):
    async def scenario():
        existing = channel.send.return_value
        channel.history.side_effect = lambda **kwargs: history([existing])
        result = await controller.publisher.ensure(
            controller.authorization.owner_id, channel, DashboardView(controller)
        )
        assert result.message is existing
        channel.send.assert_not_awaited()
        assert saved_settings.get.return_value.dashboard.message_id == existing.id

    asyncio.run(scenario())


def test_failed_db_commit_can_retry_without_duplicate_send(controller, channel, settings_mock):
    async def scenario():
        view = DashboardView(controller)
        settings_mock.save_dashboard.side_effect = RuntimeError("simulated commit failure")
        with pytest.raises(RuntimeError):
            await controller.publisher.ensure(controller.authorization.owner_id, channel, view)
        assert controller.publisher._pending is not None
        settings_mock.save_dashboard.side_effect = None
        await controller.publisher.ensure(controller.authorization.owner_id, channel, view)
        channel.send.assert_awaited_once()
        assert controller.publisher._pending is None

    asyncio.run(scenario())


@pytest.mark.parametrize("bad_channel", ["public", "not_text"])
def test_first_publish_requires_private_text_channel(
    controller, channel, settings_mock, bad_channel
):
    async def scenario():
        target = channel
        if bad_channel == "public":
            channel.permissions_for.return_value.view_channel = True
        else:
            target = SimpleNamespace(send=AsyncMock())
        with pytest.raises(DashboardPublishError):
            await controller.publisher.ensure(
                controller.authorization.owner_id, target, DashboardView(controller)
            )
        channel.send.assert_not_awaited()
        settings_mock.save_dashboard.assert_not_awaited()

    asyncio.run(scenario())


def test_saved_non_nova_message_is_never_overwritten(controller, channel, saved_settings):
    async def scenario():
        message = channel.send.return_value
        saved_settings.get.return_value = replace(
            saved_settings.get.return_value, dashboard=DashboardLocation(channel.id, message.id)
        )
        message.author = SimpleNamespace(id=999)
        with pytest.raises(DashboardPublishError):
            await controller.publisher.ensure(
                controller.authorization.owner_id, channel, DashboardView(controller)
            )
        message.edit.assert_not_awaited()
        channel.send.assert_not_awaited()

    asyncio.run(scenario())


def test_publisher_denies_non_owner_before_any_io(controller, channel, settings_mock):
    async def scenario():
        with pytest.raises(AuthorizationError):
            await controller.publisher.ensure(
                controller.authorization.owner_id + 1, channel, DashboardView(controller)
            )
        settings_mock.get.assert_not_awaited()
        channel.send.assert_not_awaited()

    asyncio.run(scenario())


def test_anchor_refresh_is_the_only_navigation_that_edits_shared_message(
    controller, channel, saved_settings, interaction
):
    async def scenario():
        saved_settings.get.return_value = replace(
            saved_settings.get.return_value,
            dashboard=DashboardLocation(interaction.channel_id, interaction.message.id),
        )
        interaction.channel = channel
        await controller.refresh_anchor(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        interaction.message.edit.assert_awaited_once()
        assert "Đã làm mới" in interaction.edit_original_response.await_args.kwargs["content"]

    asyncio.run(scenario())


def test_persistent_dashboard_resumes_from_sqlite_after_client_restart(
    settings, channel, interaction
):
    async def boot():
        client = NovaClient(settings, Database(settings.database_url))
        client._connection.user = channel.send.return_value.author
        with patch.object(client.tree, "sync", new=AsyncMock(return_value=[])):
            await client.setup_hook()
        return client

    async def scenario():
        first = await boot()
        try:
            await first.dashboard.publisher.ensure(
                settings.owner_id, channel, DashboardView(first.dashboard)
            )
        finally:
            await first.close()
        restarted = await boot()
        try:
            saved = await restarted.settings_service.get(settings.owner_id)
            assert saved.dashboard == DashboardLocation(channel.id, channel.send.return_value.id)
            restored_view = restarted.persistent_views[0]
            assert restored_view.is_persistent()
            interaction.channel_id = channel.id
            interaction.message.id = channel.send.return_value.id
            tasks = next(
                item for item in restored_view.children if getattr(item, "screen", None) == "tasks"
            )
            await tasks.callback(interaction)
            assert (
                "Task Management"
                in interaction.edit_original_response.await_args.kwargs["embed"].title
            )
            interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
            channel.send.assert_awaited_once()
            interaction.message.edit.assert_not_awaited()
        finally:
            await restarted.close()

    asyncio.run(scenario())
