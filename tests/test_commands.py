import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import discord
import pytest
from discord import app_commands

from app.discord_bot.commands.foundation import FoundationCommands
from app.discord_bot.error_handlers import ERROR_MESSAGE, handle_command_error, send_private
from app.discord_bot.renderers.dashboard import MODULES


def test_ping_returns_online_status_privately(interaction, authorization):
    asyncio.run(FoundationCommands(authorization).ping(interaction))
    sender = interaction.response.send_message
    assert sender.await_args.args == ("Pong! NOVA đang online.",)
    assert sender.await_args.kwargs["ephemeral"] is True


def test_menu_contains_exactly_requested_modules_without_metrics(interaction, authorization):
    asyncio.run(FoundationCommands(authorization).menu(interaction))
    kwargs = interaction.response.send_message.await_args.kwargs
    assert kwargs["ephemeral"] is True
    embed = kwargs["embed"]
    assert embed.title == "NOVA — PERSONAL CONTROL CENTER"
    assert tuple(field.name for field in embed.fields) == MODULES
    assert len(embed.fields) == 11
    assert all(field.value == "Sắp ra mắt" for field in embed.fields)
    assert "view" not in kwargs  # No Phase 2 components.


@pytest.mark.parametrize("command", ["ping", "menu"])
def test_direct_command_callbacks_also_deny_non_owner(interaction, authorization, command):
    interaction.user.id += 1
    with patch("app.discord_bot.commands.foundation.render_dashboard") as renderer:
        asyncio.run(getattr(FoundationCommands(authorization), command)(interaction))
    renderer.assert_not_called()
    sender = interaction.response.send_message
    assert sender.await_args.kwargs["ephemeral"] is True
    assert "embed" not in sender.await_args.kwargs
    assert sender.await_args.args == ("Chỉ chủ tài khoản được sử dụng NOVA.",)


@pytest.mark.parametrize("responded", [False, True])
def test_command_error_is_safe_and_supports_deferred_response(interaction, caplog, responded):
    interaction.response.is_done.return_value = responded
    error = app_commands.CommandInvokeError(
        SimpleNamespace(name="menu"), RuntimeError("private contents must not leak")
    )
    asyncio.run(handle_command_error(interaction, error))
    sender = interaction.followup.send if responded else interaction.response.send_message
    assert sender.await_args.args == (ERROR_MESSAGE,)
    assert sender.await_args.kwargs["ephemeral"] is True
    assert "private contents" not in caplog.text
    assert caplog.records[-1].interaction_id == interaction.id
    assert caplog.records[-1].error_type == "RuntimeError"


def test_expired_interaction_does_not_raise(interaction, caplog):
    response = type("Response", (), {"status": 404, "reason": "Not Found"})()
    interaction.response.send_message.side_effect = discord.NotFound(response, "private HTTP text")
    asyncio.run(send_private(interaction, "Safe response"))
    assert "interaction_response_failed" in caplog.text
    assert "private HTTP text" not in caplog.text
