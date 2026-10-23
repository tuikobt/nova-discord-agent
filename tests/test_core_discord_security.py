import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.discord_bot.core_state import CoreRoute, WriteIntent
from app.discord_bot.views.core import ConfirmationView, CorePanelView
from app.discord_bot.views.core_forms import CoreFormModal, FormDraft
from app.discord_bot.views.core_pickers import DateChoice, DatePickerView
from app.domain.approvals import ApprovalRequest
from app.domain.core import Page, TaskData
from app.domain.modules import Screen

START = datetime(2026, 10, 25, 13, tzinfo=UTC)


@pytest.mark.parametrize(
    "entry",
    [
        "view",
        "button",
        "select",
        "modal_check",
        "modal_submit",
        "date_check",
        "date_submit",
        "approve",
        "reject",
        "controller_open",
        "controller_commit",
        "controller_error",
        "controller_picker",
    ],
)
def test_all_core_ui_entrypoints_deny_non_owner_before_database(
    controller, interaction, core_services_mock, entry
):
    async def scenario():
        core = controller.core
        route = CoreRoute(Screen.TASKS)
        view = CorePanelView(core, route, "UTC", page=Page((), 0, 0, 5))
        draft = FormDraft(route, "UTC")
        modal = CoreFormModal(core, view, draft)
        picker = DatePickerView(
            core,
            DateChoice(
                route, "UTC", route, "day", START.replace(tzinfo=None), view.expires_at, True
            ),
        )
        data = TaskData(title="Private")
        intent = WriteIntent(route, data)
        request = ApprovalRequest(
            "private-token", "cancel_task", datetime.now(UTC) + timedelta(minutes=5), None, data, ()
        )
        confirm = ConfirmationView(core, route, "UTC", intent, request, ("Private change",))
        interaction.user.id += 1
        if entry == "view":
            assert not await view.interaction_check(interaction)
        elif entry == "button":
            await view.children[2].callback(interaction)
        elif entry == "select":
            select = next(
                item for item in view.children if getattr(item, "action", None) == "filter_status"
            )
            select._values = ["todo"]
            await select.callback(interaction)
        elif entry == "modal_check":
            assert not await modal.interaction_check(interaction)
        elif entry == "modal_submit":
            await modal.on_submit(interaction)
        elif entry == "date_check":
            assert not await picker.interaction_check(interaction)
        elif entry == "date_submit":
            await picker.children[4].callback(interaction)
        elif entry in ("approve", "reject"):
            await next(
                item for item in confirm.children if getattr(item, "action", None) == entry
            ).callback(interaction)
        elif entry == "controller_open":
            await core.open(interaction, route)
        elif entry == "controller_commit":
            await core.commit(interaction, intent, view)
        elif entry == "controller_picker":
            await core.pick_link(interaction, view)
        else:
            await core.error(interaction, RuntimeError("private"), route)
        interaction.edit_original_response.assert_not_awaited()
        interaction.response.send_modal.assert_not_awaited()
        assert interaction.response.send_message.await_args.kwargs["ephemeral"]
        for service in (
            core_services_mock.tasks,
            core_services_mock.projects,
            core_services_mock.calendar,
        ):
            service.create.assert_not_awaited()
            service.update.assert_not_awaited()
            service.list.assert_not_awaited()
        controller.settings.get.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("expired", ["modal", "view", "stopped", "date"])
def test_expired_or_replaced_core_views_and_forms_never_write(
    controller, interaction, core_services_mock, expired
):
    async def scenario():
        route = CoreRoute(Screen.TASKS)
        view = CorePanelView(controller.core, route, "UTC", page=Page((), 0, 0, 5))
        modal = CoreFormModal(controller.core, view, FormDraft(route, "UTC"))
        if expired == "modal":
            modal.expires_at = 0
            await modal.on_submit(interaction)
        elif expired == "date":
            picker = DatePickerView(
                controller.core,
                DateChoice(
                    route, "UTC", route, "day", START.replace(tzinfo=None), view.expires_at, True
                ),
            )
            picker.expires_at = 0
            await picker.children[4].callback(interaction)
        else:
            if expired == "view":
                view.expires_at = 0
            else:
                view.stop()
            await view.children[2].callback(interaction)
            await modal.on_submit(interaction)
        core_services_mock.tasks.create.assert_not_awaited()
        interaction.edit_original_response.assert_not_awaited()
        interaction.response.send_modal.assert_not_awaited()

    asyncio.run(scenario())


def test_form_uses_snapshot_timezone_and_preserves_untouched_datetime_precision():
    stamp = START.replace(second=15, microsecond=123456)
    record = type(
        "Record",
        (),
        {
            "id": "id",
            "name": "P",
            "description": "Notes",
            "status": "paused",
            "deadline_at": stamp,
            "created_at": START,
            "updated_at": START,
        },
    )()
    draft = FormDraft(CoreRoute(Screen.PROJECTS, item_id="id"), "Asia/Ho_Chi_Minh", record=record)
    draft.raw = {**draft.defaults(), "name": "Edited"}
    intent = draft.parse()
    assert intent.data.deadline_at == stamp
    assert intent.data.status == "paused" and intent.data.description == "Notes"
    draft.raw["deadline_at"] = "2026-10-25 21:00"
    assert draft.parse().data.deadline_at == START + timedelta(hours=1)


def test_modal_limits_and_timeout_controls_are_valid_legacy_components(controller):
    async def scenario():
        for screen in (Screen.TASKS, Screen.PROJECTS, Screen.CALENDAR):
            route = CoreRoute(screen, day=START.date())
            view = CorePanelView(controller.core, route, "Asia/Ho_Chi_Minh", page=Page((), 0, 0, 5))
            modal = CoreFormModal(controller.core, view, FormDraft(route, view.timezone))
            assert len(modal.children) <= 5 and modal.timeout == 300
            assert all(item.max_length <= 4000 for item in modal.children)
            assert view.timeout == 600 and not view.is_persistent()
            assert len(view.to_components()) <= 5
            assert all(len(item.custom_id) <= 100 for item in view.children)
            view.message = type("Message", (), {"edit": AsyncMock()})()
            await view.on_timeout()
            assert all(child.disabled for child in view.children)
            assert "hết hạn" in view.message.edit.await_args.kwargs["content"]

    asyncio.run(scenario())


def test_pending_approval_expires_on_backend_even_before_ui_timer(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            task = await env.tasks.create(env.owner, TaskData(title="T"), request_id="t")
            await dashboard.core.open(interaction, CoreRoute(Screen.TASKS, item_id=task.id))
            view = interaction.edit_original_response.await_args.kwargs["view"]
            select = next(
                item for item in view.children if getattr(item, "action", None) == "status"
            )
            select._values = ["cancelled"]
            interaction.response.is_done.return_value = False
            await select.callback(interaction)
            confirm = interaction.edit_original_response.await_args.kwargs["view"]
            assert isinstance(confirm, ConfirmationView)
            dashboard.core.services.tasks.approvals.clock = lambda: (
                datetime.now(UTC) + timedelta(hours=1)
            )
            interaction.response.is_done.return_value = False
            await next(
                item for item in confirm.children if getattr(item, "action", None) == "approve"
            ).callback(interaction)
            assert (await env.tasks.get(env.owner, task.id)).status == "todo"
            assert (
                "Xác nhận"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )

    asyncio.run(scenario())


def test_storage_retry_keeps_request_id_and_never_leaks_exception_payload(
    core_ui_factory, interaction, caplog, monkeypatch
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await dashboard.core.open(interaction, CoreRoute(Screen.TASKS))
            view = interaction.edit_original_response.await_args.kwargs["view"]
            data = TaskData(title="T")
            intent = WriteIntent(view.route, data)
            service = dashboard.core.services.tasks
            from app.domain.errors import StorageError

            with monkeypatch.context() as patch:
                patch.setattr(service, "create", AsyncMock(side_effect=StorageError()))
                await dashboard.core.commit(interaction, intent, view)
            error_view = interaction.edit_original_response.await_args.kwargs["view"]
            assert error_view.intent is intent
            assert (await env.tasks.list(env.owner)).total == 0
            interaction.response.is_done.return_value = False
            await next(
                item
                for item in error_view.children
                if getattr(item, "action", None) == "retry_write"
            ).callback(interaction)
            assert (await env.tasks.list(env.owner)).total == 1
            assert intent.saved is not None
            assert any(
                getattr(record, "error_type", None) == "StorageError" for record in caplog.records
            )
            assert "private-token" not in caplog.text

    asyncio.run(scenario())
