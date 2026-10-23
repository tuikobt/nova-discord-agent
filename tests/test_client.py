import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import User, UserSettings
from app.db.session import Database
from app.discord_bot.client import NovaClient


@pytest.mark.parametrize("guild_id", [None, 234567890123456789])
def test_startup_bootstraps_before_sync_once_and_closes_resources(settings, guild_id):
    from dataclasses import replace

    async def scenario():
        database = Database(settings.database_url)
        client = NovaClient(replace(settings, guild_id=guild_id), database)
        assert {command.name for command in client.tree.get_commands()} == {
            "ping",
            "menu",
            "help",
            "settings",
        }
        assert not client.intents.message_content
        assert not client.intents.members
        assert not client.intents.presences
        with (
            patch.object(database, "initialize", new=AsyncMock()) as initialize,
            patch.object(client.settings_service, "initialize_owner", new=AsyncMock()) as bootstrap,
            patch.object(client.dashboard, "restore", new=AsyncMock()) as restore,
            patch.object(client.tree, "sync", new=AsyncMock(return_value=[None, None])) as sync,
            patch.object(database, "close", wraps=database.close) as close,
        ):

            async def verify_bootstrap_before_sync(**kwargs):
                initialize.assert_awaited_once()
                bootstrap.assert_awaited_once_with(settings.owner_id, settings.timezone)
                restore.assert_awaited_once()
                return [None, None]

            sync.side_effect = verify_bootstrap_before_sync
            await client.setup_hook()
            await client.on_ready()
            await client.on_ready()
            sync.assert_awaited_once()
            if guild_id:
                assert sync.await_args.kwargs["guild"].id == guild_id
            else:
                assert sync.await_args.kwargs == {}
            await client.close()
            close.assert_awaited_once()

    asyncio.run(scenario())


def test_bootstrap_failure_does_not_sync_commands(settings):
    async def scenario():
        database = Database(settings.database_url)
        client = NovaClient(settings, database)
        try:
            with (
                patch.object(database, "initialize", new=AsyncMock(side_effect=RuntimeError)),
                patch.object(client.tree, "sync", new=AsyncMock()) as sync,
            ):
                with pytest.raises(RuntimeError):
                    await client.setup_hook()
                sync.assert_not_awaited()
        finally:
            await client.close()

    asyncio.run(scenario())


def test_client_bootstrap_with_real_database_and_mocked_discord_sync(settings):
    async def scenario():
        database = Database(settings.database_url)
        client = NovaClient(settings, database)
        try:

            async def verify_persisted_owner(**kwargs):
                async with database.sessions() as session:
                    assert await session.get(User, str(settings.owner_id)) is not None
                    assert await session.get(UserSettings, str(settings.owner_id)) is not None
                return []

            with patch.object(client.tree, "sync", side_effect=verify_persisted_owner):
                await client.setup_hook()
                assert len(client.persistent_views) == 1
                assert client.persistent_views[0].is_persistent()
        finally:
            await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("owner", [True, False])
def test_tree_guard_covers_slash_dispatch(settings, interaction, owner):
    async def scenario():
        database = Database(settings.database_url)
        client = NovaClient(settings, database)
        try:
            if not owner:
                interaction.user.id += 1
            assert await client.tree.interaction_check(interaction) is owner
        finally:
            await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "owner,bot,guild",
    [(True, False, None), (False, False, None), (True, True, None), (True, False, object())],
)
def test_dm_entrypoint_is_owner_only_and_ignores_server_messages(settings, owner, bot, guild):
    async def scenario():
        database = Database(settings.database_url)
        client = NovaClient(settings, database)
        message = SimpleNamespace(
            author=SimpleNamespace(
                id=settings.owner_id if owner else settings.owner_id + 1, bot=bot
            ),
            guild=guild,
            channel=SimpleNamespace(send=AsyncMock()),
        )  # Deliberately no .content: Foundation must not read the message.
        try:
            await client.on_message(message)
            if owner and not bot and guild is None:
                message.channel.send.assert_awaited_once()
                assert "Sắp ra mắt" in message.channel.send.await_args.args[0]
            else:
                message.channel.send.assert_not_awaited()
        finally:
            await client.close()

    asyncio.run(scenario())


def test_event_error_handler_does_not_log_payloads(settings, caplog):
    async def scenario():
        database = Database(settings.database_url)
        client = NovaClient(settings, database)
        try:
            await client.on_error("on_message", "private contents", token="never-log-this")
            assert "discord_event_failed" in caplog.text
            assert "private contents" not in caplog.text
            assert "never-log-this" not in caplog.text
        finally:
            await client.close()

    asyncio.run(scenario())
