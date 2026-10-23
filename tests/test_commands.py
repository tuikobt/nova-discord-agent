import asyncio
from types import SimpleNamespace

import discord
import pytest
from discord import app_commands

from app.discord_bot.commands.foundation import FoundationCommands
from app.discord_bot.error_handlers import ERROR_MESSAGE, handle_command_error, send_private
from app.domain.modules import Screen


def test_ping_returns_online_status_privately(interaction, authorization, command_controller):
    asyncio.run(FoundationCommands(authorization, command_controller).ping(interaction))
    sender = interaction.response.send_message
    assert sender.await_args.args == ("Pong! NOVA đang online.",)
    assert sender.await_args.kwargs["ephemeral"] is True


def test_menu_delegates_to_dashboard(interaction, authorization, command_controller):
    asyncio.run(FoundationCommands(authorization, command_controller).menu(interaction))
    command_controller.menu.assert_awaited_once_with(interaction)


@pytest.mark.parametrize("command", ["ping", "menu", "help", "settings"])
def test_direct_command_callbacks_also_deny_non_owner(
    interaction, authorization, command, command_controller
):
    interaction.user.id += 1
    asyncio.run(
        getattr(FoundationCommands(authorization, command_controller), command)(interaction)
    )
    command_controller.menu.assert_not_awaited()
    command_controller.navigate.assert_not_awaited()
    sender = interaction.response.send_message
    assert sender.await_args.kwargs["ephemeral"] is True
    assert "embed" not in sender.await_args.kwargs
    assert sender.await_args.args == ("Chỉ chủ tài khoản được sử dụng NOVA.",)


@pytest.mark.parametrize("command,screen", [("help", Screen.HELP), ("settings", Screen.SETTINGS)])
def test_private_shortcuts(interaction, authorization, command_controller, command, screen):
    asyncio.run(
        getattr(FoundationCommands(authorization, command_controller), command)(interaction)
    )
    command_controller.navigate.assert_awaited_once_with(interaction, screen, new_panel=True)


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
