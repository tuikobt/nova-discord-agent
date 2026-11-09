import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import discord
import pytest

from app.discord_bot.views.dashboard import (
    DashboardView,
    EditTimezoneButton,
    MoreSelect,
    PanelView,
    TimezoneModal,
)
from app.domain.core import Page
from app.domain.modules import MODULES, MORE_SCREENS, QUICK_SCREENS, Screen
from app.domain.schemas import DashboardLocation


def test_dashboard_components_are_persistent_and_stable(controller):
    async def scenario():
        first, second = DashboardView(controller), DashboardView(controller)
        assert first.is_persistent()
        assert first.timeout is None
        assert [item.custom_id for item in first.children] == [
            item.custom_id for item in second.children
        ]
        assert len({item.custom_id for item in first.children}) == len(first.children)
        assert len(first.children) == 9
        assert all(
            str(controller.authorization.owner_id) not in item.custom_id for item in first.children
        )
        assert all(len(item.custom_id) <= 100 for item in first.children)
        quick_buttons = [
            item for item in first.children if getattr(item, "screen", None) in QUICK_SCREENS
        ]
        assert {item.screen for item in quick_buttons} == set(QUICK_SCREENS)
        assert [sum(item.row == row for item in quick_buttons) for row in (0, 1)] == [3, 2]
        select = next(item for item in first.children if isinstance(item, MoreSelect))
        assert {option.value for option in select.options} == set(MORE_SCREENS)

    asyncio.run(scenario())


@pytest.mark.parametrize("screen", list(Screen))
def test_every_screen_renders_in_a_private_panel(controller, interaction, screen):
    async def scenario():
        await controller.navigate(interaction, screen, new_panel=True)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        kwargs = interaction.edit_original_response.await_args.kwargs
        assert isinstance(kwargs["embed"], discord.Embed)
        view = kwargs["view"]
        assert view.timeout == 600
        assert not view.is_persistent()
        if screen != Screen.HOME:
            assert {getattr(item, "label", None) for item in view.children} >= {"Back", "Refresh"}
        if screen in MODULES and not MODULES[screen].available:
            assert "Sắp ra mắt" in str(kwargs["embed"].to_dict())
        interaction.message.edit.assert_not_awaited()

    asyncio.run(scenario())


def test_public_button_opens_private_panel_without_overwriting_anchor(
    controller, interaction, settings_mock
):
    async def scenario():
        settings_mock.get.return_value = replace(
            settings_mock.get.return_value,
            dashboard=DashboardLocation(interaction.channel_id, interaction.message.id),
        )
        view = DashboardView(controller)
        button = next(
            item for item in view.children if getattr(item, "screen", None) == Screen.TASKS
        )
        await button.callback(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        assert (
            "Task Management" in interaction.edit_original_response.await_args.kwargs["embed"].title
        )
        interaction.message.edit.assert_not_awaited()
        assert not view.is_finished()

    asyncio.run(scenario())


def test_back_refresh_and_next_edit_only_current_private_panel(
    controller, interaction, core_services_mock
):
    async def scenario():
        core_services_mock.tasks.list.side_effect = lambda actor, **kwargs: Page(
            (), 6, kwargs["page"], 5
        )
        await controller.navigate(interaction, Screen.TASKS, new_panel=True)
        interaction.response.defer.reset_mock()
        interaction.response.is_done.return_value = False
        view = interaction.edit_original_response.await_args.kwargs["view"]
        next_button = next(item for item in view.children if getattr(item, "label", None) == "Next")
        await next_button.callback(interaction)
        interaction.response.defer.assert_awaited_once_with()
        kwargs = interaction.edit_original_response.await_args.kwargs
        assert "Trang 2/2" in kwargs["embed"].footer.text
        assert view.is_finished()
        second = kwargs["view"]
        assert next(
            item for item in second.children if getattr(item, "label", None) == "Next"
        ).disabled
        await next(
            item for item in second.children if getattr(item, "label", None) == "Refresh"
        ).callback(interaction)
        assert (
            "Trang 2/2" in interaction.edit_original_response.await_args.kwargs["embed"].footer.text
        )
        third = interaction.edit_original_response.await_args.kwargs["view"]
        await next(
            item for item in third.children if getattr(item, "label", None) == "Back"
        ).callback(interaction)
        assert interaction.edit_original_response.await_args.kwargs["embed"].title.endswith(
            "CONTROL CENTER"
        )
        interaction.response.send_message.assert_not_awaited()
        interaction.message.edit.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "entry",
    [
        "button",
        "select",
        "timezone_button",
        "modal_check",
        "modal_submit",
        "view",
        "menu",
        "anchor_refresh",
    ],
)
def test_all_ui_entrypoints_deny_non_owner(controller, interaction, settings_mock, entry):
    async def scenario():
        interaction.user.id += 1
        view = PanelView(controller, Screen.SETTINGS)
        modal = TimezoneModal(controller, "UTC", view)
        if entry == "button":
            await view.children[0].callback(interaction)
        elif entry == "select":
            select = MoreSelect(controller, anchor=True)
            select._values = [Screen.NOTES]
            await select.callback(interaction)
        elif entry == "timezone_button":
            await next(
                item for item in view.children if isinstance(item, EditTimezoneButton)
            ).callback(interaction)
        elif entry == "modal_check":
            assert not await modal.interaction_check(interaction)
        elif entry == "modal_submit":
            modal.timezone_input._value = "UTC"
            await modal.on_submit(interaction)
        elif entry == "view":
            assert not await view.interaction_check(interaction)
        elif entry == "menu":
            await controller.menu(interaction)
        else:
            await controller.refresh_anchor(interaction)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
        settings_mock.get.assert_not_awaited()
        settings_mock.update_timezone.assert_not_awaited()
        interaction.edit_original_response.assert_not_awaited()
        interaction.response.send_modal.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("screen", MORE_SCREENS)
def test_select_routes_each_module(controller, interaction, screen):
    async def scenario():
        select = MoreSelect(controller, anchor=False)
        select._values = [screen.value]
        await select.callback(interaction)
        assert (
            MODULES[screen].title
            in interaction.edit_original_response.await_args.kwargs["embed"].title
        )

    asyncio.run(scenario())


def test_select_rejects_forged_route(controller, interaction, settings_mock):
    async def scenario():
        select = MoreSelect(controller, anchor=False)
        select._values = ["settings"]
        await select.callback(interaction)
        settings_mock.get.assert_not_awaited()
        assert "không hợp lệ" in interaction.response.send_message.await_args.args[0]

    asyncio.run(scenario())


def test_timezone_modal_opens_without_db_delay_and_saves_after_validation(
    controller, interaction, settings_mock
):
    async def scenario():
        panel = PanelView(controller, Screen.SETTINGS, timezone_default="UTC")
        button = next(item for item in panel.children if isinstance(item, EditTimezoneButton))
        await button.callback(interaction)
        settings_mock.get.assert_not_awaited()
        modal = interaction.response.send_modal.await_args.args[0]
        assert modal.timezone_input.default == "UTC"
        modal.timezone_input._value = "Asia/Ho_Chi_Minh"
        await modal.on_submit(interaction)
        settings_mock.update_timezone.assert_awaited_once_with(
            interaction.user.id, "Asia/Ho_Chi_Minh"
        )
        assert "Đã lưu" in interaction.edit_original_response.await_args.kwargs["embed"].description
        assert panel.is_finished()

    asyncio.run(scenario())


@pytest.mark.parametrize("expired", [True, False])
def test_modal_expiry_or_invalid_timezone_never_writes(
    controller, interaction, settings_mock, expired
):
    async def scenario():
        modal = TimezoneModal(controller, "UTC", PanelView(controller, Screen.SETTINGS))
        modal.timezone_input._value = "UTC" if expired else "Mars/Nowhere"
        if expired:
            modal.expires_at = 0
        await modal.on_submit(interaction)
        settings_mock.update_timezone.assert_not_awaited()
        interaction.edit_original_response.assert_not_awaited()
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    asyncio.run(scenario())


def test_db_failure_has_safe_error_and_retry_controls(
    controller, interaction, settings_mock, caplog
):
    async def scenario():
        settings_mock.get.side_effect = RuntimeError("private details must not leak")
        await controller.navigate(interaction, Screen.SETTINGS, new_panel=True)
        kwargs = interaction.edit_original_response.await_args.kwargs
        assert "Chưa thể tải" in kwargs["embed"].title
        assert {item.label for item in kwargs["view"].children} >= {"Back", "Refresh"}
        assert "private details" not in caplog.text + str(kwargs["embed"].to_dict())
        settings_mock.get.side_effect = None
        await next(item for item in kwargs["view"].children if item.label == "Refresh").callback(
            interaction
        )
        assert (
            interaction.edit_original_response.await_args.kwargs["embed"].title == "NOVA — Settings"
        )

    asyncio.run(scenario())


def test_expired_panel_disables_buttons_and_preserves_anchor(controller):
    async def scenario():
        view = PanelView(controller, Screen.TASKS)
        view.message = type("Message", (), {"edit": AsyncMock()})()
        await view.on_timeout()
        assert all(item.disabled for item in view.children)
        assert "hết hạn" in view.message.edit.await_args.kwargs["content"]

    asyncio.run(scenario())


def test_stale_anchor_returns_private_recovery_message(controller, interaction):
    async def scenario():
        await controller.navigate(interaction, Screen.SETTINGS, from_anchor=True)
        embed = interaction.edit_original_response.await_args.kwargs["embed"]
        assert "đã cũ" in embed.description
        interaction.message.edit.assert_not_awaited()

    asyncio.run(scenario())


def test_restore_registers_saved_message_id_and_stable_view(
    controller, settings_mock, discord_client
):
    async def scenario():
        settings_mock.get.return_value = replace(
            settings_mock.get.return_value, dashboard=DashboardLocation(123, 456)
        )
        await controller.restore()
        args, kwargs = discord_client.add_view.call_args
        assert args[0].is_persistent()
        assert kwargs["message_id"] == 456

    asyncio.run(scenario())


def test_dm_menu_is_private_and_does_not_publish_anchor(controller, interaction):
    async def scenario():
        controller.publisher.ensure = AsyncMock()
        await controller.menu(interaction)
        controller.publisher.ensure.assert_not_awaited()
        assert interaction.edit_original_response.await_args.kwargs["embed"].title.endswith(
            "CONTROL CENTER"
        )
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)

    asyncio.run(scenario())


def test_failed_timezone_commit_does_not_report_saved(controller, interaction, settings_mock):
    async def scenario():
        settings_mock.update_timezone.side_effect = RuntimeError("private failure")
        await controller.save_timezone(interaction, "UTC")
        embed = interaction.edit_original_response.await_args.kwargs["embed"]
        assert "Đã lưu" not in embed.description
        assert "Chưa thể tải" in embed.title

    asyncio.run(scenario())


def test_expired_interaction_error_is_contained(controller, interaction, caplog):
    async def scenario():
        from types import SimpleNamespace

        interaction.edit_original_response.side_effect = discord.NotFound(
            SimpleNamespace(status=404, reason="test"), "private expired response"
        )
        await controller.navigate(interaction, Screen.HOME, new_panel=True)
        assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
        assert "private expired response" not in caplog.text

    asyncio.run(scenario())


def test_panel_expiry_remains_before_ephemeral_token_expiration(controller, interaction):
    async def scenario():
        view = PanelView(controller, Screen.SETTINGS)
        with patch("app.discord_bot.views.dashboard.monotonic", return_value=view.expires_at - 1):
            assert await view.interaction_check(interaction)
            assert 0 < view.timeout <= 1
        with patch("app.discord_bot.views.dashboard.monotonic", return_value=view.expires_at + 1):
            assert not await view.interaction_check(interaction)
        assert "hết hạn" in interaction.response.send_message.await_args.args[0]

    asyncio.run(scenario())
