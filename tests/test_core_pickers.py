"""Exercise the real draft/picker callbacks with temporary SQLite and mocked Discord."""

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import discord
import pytest

from app.discord_bot.core_state import CoreRoute
from app.discord_bot.views.core import ConfirmationView, CoreErrorView, CorePanelView
from app.discord_bot.views.core_forms import CoreFormModal, FormDraft
from app.discord_bot.views.core_pickers import (
    DateChoice,
    DatePickerView,
    DeadlineRange,
    DeadlineRangeView,
    DraftLinkView,
    DraftView,
    render_date_picker,
    render_draft,
)
from app.domain.core import EventData, Page, ProjectData, TaskData
from app.domain.modules import Screen

DAY = date(2026, 10, 25)
START = datetime(2026, 10, 25, 13, tzinfo=UTC)


def current(interaction):
    return interaction.edit_original_response.await_args.kwargs["view"]


async def press(interaction, view, label):
    interaction.response.is_done.return_value = False
    await next(item for item in view.children if getattr(item, "label", None) == label).callback(
        interaction
    )


async def choose(interaction, view, action, value):
    interaction.response.is_done.return_value = False
    select = next(item for item in view.children if getattr(item, "action", None) == action)
    select._values = [value]
    await select.callback(interaction)


async def text(interaction, modal, **values):
    for key, item in modal.inputs.items():
        item._value = values.get(key, item.default or "")
    interaction.response.is_done.return_value = False
    await modal.on_submit(interaction)


async def start_draft(interaction, dashboard, screen, **values):
    await dashboard.core.open(interaction, CoreRoute(screen, day=DAY))
    await press(interaction, current(interaction), "Thêm")
    modal = interaction.response.send_modal.await_args.args[0]
    assert (
        not {"starts_at", "ends_at", "is_fixed", "due_at", "deadline_at", "estimated_minutes"}
        & modal.inputs.keys()
    )
    await text(interaction, modal, **values)
    assert isinstance(current(interaction), DraftView)
    return current(interaction)


async def pick_time(interaction, label, hour, minute):
    await press(interaction, current(interaction), label)
    assert isinstance(current(interaction), DatePickerView)
    await choose(interaction, current(interaction), "picker_hour", str(hour))
    await choose(interaction, current(interaction), "picker_minute", str(minute))
    await press(interaction, current(interaction), "Dùng ngày giờ")


def test_calendar_entire_picker_flow_saves_only_on_explicit_save(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            task = await env.tasks.create(env.owner, TaskData(title="Linked task"), request_id="t")
            await start_draft(interaction, dashboard, Screen.CALENDAR, title="Học Python")
            assert (await env.calendar.list_day(env.owner, DAY)).total == 0
            await pick_time(interaction, "Chọn bắt đầu", 20, 30)
            await choose(interaction, current(interaction), "draft_duration", "60")
            await choose(interaction, current(interaction), "draft_fixed", "yes")
            await press(interaction, current(interaction), "Chọn công việc")
            await choose(interaction, current(interaction), "draft_link_value", task.id)
            draft = current(interaction)
            assert draft.draft.values()["ends_at"] == "2026-10-25 21:30"
            assert (await env.calendar.list_day(env.owner, DAY)).total == 0
            await press(interaction, draft, "Lưu")
            saved = current(interaction).record
            assert saved.starts_at == START + timedelta(minutes=30)
            assert saved.ends_at == START + timedelta(minutes=90)
            assert saved.is_fixed and saved.task_id == task.id
            assert (await env.calendar.list_day(env.owner, DAY)).total == 1
            interaction.message.edit.assert_not_awaited()

    asyncio.run(scenario())


def test_task_deadline_priority_estimate_link_and_clear_from_draft(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            project = await env.projects.create(env.owner, ProjectData(name="P"), request_id="p")
            await start_draft(interaction, dashboard, Screen.TASKS, title="T", description="Notes")
            await pick_time(interaction, "Chọn deadline", 21, 0)
            await choose(interaction, current(interaction), "draft_priority", "high")
            await choose(interaction, current(interaction), "draft_estimate", "45")
            await press(interaction, current(interaction), "Chọn dự án")
            await choose(interaction, current(interaction), "draft_link_value", project.id)
            assert (await env.tasks.list(env.owner)).total == 0
            await press(interaction, current(interaction), "Lưu")
            row = current(interaction).record
            assert row.priority == "high" and row.estimated_minutes == 45
            assert row.due_at == START + timedelta(hours=1) and row.project_id == project.id
            await press(interaction, current(interaction), "Sửa")
            await text(
                interaction, interaction.response.send_modal.await_args.args[0], title="Edited"
            )
            await press(interaction, current(interaction), "Bỏ deadline")
            await press(interaction, current(interaction), "Lưu")
            saved = current(interaction).record
            assert saved.due_at is None and saved.description == "Notes"
            assert saved.project_id == project.id and saved.estimated_minutes == 45

    asyncio.run(scenario())


def test_project_deadline_and_status_can_be_picked_before_first_save(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await start_draft(interaction, dashboard, Screen.PROJECTS, name="P")
            await pick_time(interaction, "Chọn deadline", 20, 0)
            await choose(interaction, current(interaction), "draft_status", "paused")
            assert (await env.projects.list(env.owner)).total == 0
            await press(interaction, current(interaction), "Lưu")
            assert current(interaction).record.deadline_at == START
            assert current(interaction).record.status == "paused"

    asyncio.run(scenario())


def test_picker_back_and_discard_never_write_or_apply_unconfirmed_selection(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            view = await start_draft(interaction, dashboard, Screen.CALENDAR, title="Draft")
            draft = view.draft
            await press(interaction, view, "Chọn bắt đầu")
            await choose(interaction, current(interaction), "picker_hour", "23")
            await press(interaction, current(interaction), "Quay lại")
            assert draft.values()["starts_at"] == ""
            await press(interaction, current(interaction), "Bỏ bản nháp")
            assert isinstance(current(interaction), CorePanelView)
            assert (await env.calendar.list_day(env.owner, DAY)).total == 0

    asyncio.run(scenario())


def test_missing_or_reversed_event_times_keep_editable_draft_without_write(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await start_draft(interaction, dashboard, Screen.CALENDAR, title="Draft")
            await press(interaction, current(interaction), "Lưu")
            assert isinstance(current(interaction), DraftView)
            assert (
                "Chọn bắt đầu"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            await choose(interaction, current(interaction), "draft_duration", "60")
            assert (
                "Chọn bắt đầu trước"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            await pick_time(interaction, "Chọn bắt đầu", 20, 0)
            await pick_time(interaction, "Chọn kết thúc", 19, 0)
            await press(interaction, current(interaction), "Lưu")
            assert isinstance(current(interaction), DraftView)
            assert (
                "sau giờ bắt đầu"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            assert (await env.calendar.list_day(env.owner, DAY)).total == 0

    asyncio.run(scenario())


def test_calendar_overlap_is_still_explicitly_approved_after_picker_save(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await env.calendar.create(
                env.owner,
                EventData(title="Existing", starts_at=START, ends_at=START + timedelta(hours=1)),
                request_id="old",
            )
            await start_draft(interaction, dashboard, Screen.CALENDAR, title="Overlap")
            await pick_time(interaction, "Chọn bắt đầu", 20, 30)
            await choose(interaction, current(interaction), "draft_duration", "60")
            await press(interaction, current(interaction), "Lưu")
            assert isinstance(current(interaction), ConfirmationView)
            assert (await env.calendar.list_day(env.owner, DAY)).total == 1
            await press(interaction, current(interaction), "Duyệt")
            assert (await env.calendar.list_day(env.owner, DAY)).total == 2

    asyncio.run(scenario())


def test_duplicate_save_and_replaced_text_modal_do_not_create_extra_records(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            view = await start_draft(interaction, dashboard, Screen.TASKS, title="Once")
            await press(interaction, view, "Sửa nội dung")
            modal = interaction.response.send_modal.await_args.args[0]
            await choose(interaction, view, "draft_priority", "high")
            await text(interaction, modal, title="Discarded old modal")
            assert current(interaction).draft.values()["title"] == "Once"
            view = current(interaction)
            await asyncio.gather(press(interaction, view, "Lưu"), press(interaction, view, "Lưu"))
            rows = await env.tasks.list(env.owner)
            assert rows.total == 1 and rows.items[0].title == "Once"

    asyncio.run(scenario())


@pytest.mark.parametrize("second_action", ["select", "modal"])
def test_form_edits_wait_for_in_flight_save_and_cannot_change_saved_payload(
    core_ui_factory, interaction, monkeypatch, second_action
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            view = await start_draft(interaction, dashboard, Screen.TASKS, title="Snapshot")
            await press(interaction, view, "Sửa nội dung")
            modal = interaction.response.send_modal.await_args.args[0]
            original_create = dashboard.core.services.tasks.create
            entered, release = asyncio.Event(), asyncio.Event()

            async def delayed_create(*args, **kwargs):
                entered.set()
                await release.wait()
                return await original_create(*args, **kwargs)

            monkeypatch.setattr(dashboard.core.services.tasks, "create", delayed_create)
            saving = asyncio.create_task(press(interaction, view, "Lưu"))
            await asyncio.wait_for(entered.wait(), timeout=5)
            edit = asyncio.create_task(
                choose(interaction, view, "draft_priority", "critical")
                if second_action == "select"
                else text(interaction, modal, title="Late edit")
            )
            release.set()
            await asyncio.wait_for(asyncio.gather(saving, edit), timeout=5)
            rows = await env.tasks.list(env.owner)
            assert rows.total == 1 and rows.items[0].title == "Snapshot"
            assert rows.items[0].priority == "medium"
            assert view.draft.values()["title"] == "Snapshot"
            assert "priority" not in view.draft.selections

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "selected, expected",
    [
        (datetime(2028, 1, 31), datetime(2028, 2, 29)),
        (datetime(2027, 1, 31), datetime(2027, 2, 28)),
        (datetime(2026, 12, 31), datetime(2027, 1, 31)),
    ],
)
def test_month_navigation_clamps_days_and_handles_leap_years(
    controller, interaction, selected, expected
):
    async def scenario():
        route = CoreRoute(Screen.CALENDAR, day=selected.date())
        state = DateChoice(route, "UTC", route, "day", selected, float("inf"), True)
        view = DatePickerView(controller.core, state)
        await press(interaction, view, "Tháng ›")
        assert current(interaction).state.selected == expected
        assert len(render_date_picker(current(interaction).state)) < 6000

    asyncio.run(scenario())


@pytest.mark.parametrize("selected", [datetime(2026, 3, 8, 2, 30), datetime(2026, 11, 1, 1, 30)])
def test_picker_rejects_nonexistent_or_ambiguous_dst_without_changing_draft(
    controller, interaction, selected
):
    async def scenario():
        draft = FormDraft(CoreRoute(Screen.CALENDAR), "America/New_York", seed_title="DST")
        state = DateChoice(
            draft.route, draft.timezone, draft, "starts_at", selected, draft.expires_at
        )
        await press(interaction, DatePickerView(controller.core, state), "Dùng ngày giờ")
        assert isinstance(current(interaction), DatePickerView)
        assert draft.values()["starts_at"] == ""
        assert (
            "không tồn tại hoặc có hai offset"
            in interaction.edit_original_response.await_args.kwargs["embed"].description
        )
        controller.core.services.calendar.create.assert_not_awaited()

    asyncio.run(scenario())


def test_advanced_time_input_is_optional_and_correctable_with_request_id_retained(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            view = await start_draft(interaction, dashboard, Screen.TASKS, title="Exact")
            key = view.draft.request_id
            await press(interaction, view, "Nhập ngày/giờ, số phút")
            modal = interaction.response.send_modal.await_args.args[0]
            await text(interaction, modal, due_at="10/11", estimated_minutes="17")
            assert isinstance(current(interaction), CoreErrorView)
            await press(interaction, current(interaction), "Nhập lại")
            retry = interaction.response.send_modal.await_args.args[0]
            assert retry.inputs["due_at"].default == "10/11" and retry.draft.request_id == key
            await text(interaction, retry, due_at="2026-10-25 20:17")
            assert (await env.tasks.list(env.owner)).total == 0
            await press(interaction, current(interaction), "Chọn deadline")
            minute = next(
                item
                for item in current(interaction).children
                if getattr(item, "action", None) == "picker_minute"
            )
            assert next(option for option in minute.options if option.value == "17").default
            await press(interaction, current(interaction), "Dùng ngày giờ")
            await press(interaction, current(interaction), "Lưu")
            saved = current(interaction).record
            assert saved.due_at == START + timedelta(minutes=17) and saved.estimated_minutes == 17

    asyncio.run(scenario())


def test_unchanged_picker_preserves_seconds_microseconds_and_other_task_fields(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            stamp = START.replace(minute=17, second=23, microsecond=123456)
            row = await env.tasks.create(
                env.owner,
                TaskData(title="Old", due_at=stamp, priority="critical", status="doing"),
                request_id="old",
            )
            await dashboard.core.open(interaction, CoreRoute(Screen.TASKS, item_id=row.id))
            await press(interaction, current(interaction), "Sửa")
            await text(interaction, interaction.response.send_modal.await_args.args[0], title="New")
            await press(interaction, current(interaction), "Chọn deadline")
            await press(interaction, current(interaction), "Dùng ngày giờ")
            await press(interaction, current(interaction), "Lưu")
            assert current(interaction).record.due_at == stamp
            assert current(interaction).record.priority == "critical"
            assert current(interaction).record.status == "doing"

    asyncio.run(scenario())


def test_deadline_range_picker_inclusive_day_filter_and_cancel(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            for key, at in (
                ("day", START),
                ("last", START + timedelta(hours=3, minutes=59)),
                ("next", START + timedelta(hours=11)),
            ):
                await env.tasks.create(env.owner, TaskData(title=key, due_at=at), request_id=key)
            await dashboard.core.open(interaction, CoreRoute(Screen.TASKS, day=DAY))
            await press(interaction, current(interaction), "Deadline")
            await press(interaction, current(interaction), "Từ ngày")
            await press(interaction, current(interaction), "Dùng ngày")
            await press(interaction, current(interaction), "Đến hết ngày")
            await press(interaction, current(interaction), "Dùng ngày")
            await press(interaction, current(interaction), "Áp dụng")
            route = current(interaction).route
            assert route.due_from == START.replace(hour=17) - timedelta(days=1)
            assert route.due_until == START.replace(hour=17)
            assert (
                "2 bản ghi"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            await press(interaction, current(interaction), "Deadline")
            await press(interaction, current(interaction), "Bỏ mốc từ")
            await press(interaction, current(interaction), "Quay lại")
            assert current(interaction).route == route

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["draft", "picker", "range", "link"])
@pytest.mark.parametrize("blocked", ["non_owner", "expired", "replaced"])
def test_every_new_view_checks_owner_expiry_and_replacement_before_callbacks(
    controller, interaction, kind, blocked
):
    async def scenario():
        route = CoreRoute(Screen.TASKS, day=DAY)
        draft = FormDraft(route, "UTC", seed_title="Private")
        views = {
            "draft": DraftView(controller.core, draft),
            "picker": DatePickerView(
                controller.core,
                DateChoice(
                    route, "UTC", draft, "due_at", START.replace(tzinfo=None), draft.expires_at
                ),
            ),
            "range": DeadlineRangeView(controller.core, DeadlineRange(route, "UTC")),
            "link": DraftLinkView(controller.core, draft, Page((), 0, 0, 5)),
        }
        view = views[kind]
        if blocked == "non_owner":
            interaction.user.id += 1
        elif blocked == "expired":
            view.expires_at = 0
        else:
            view.stop()
        await view.children[0].callback(interaction)
        await controller.core.forms.dispatch(interaction, view, "draft_save")
        interaction.edit_original_response.assert_not_awaited()
        for service in (
            controller.core.services.tasks,
            controller.core.services.projects,
            controller.core.services.calendar,
        ):
            service.create.assert_not_awaited()
            service.update.assert_not_awaited()
            service.list.assert_not_awaited()

    asyncio.run(scenario())


def test_forged_picker_select_does_not_change_selection_or_draft(controller, interaction):
    async def scenario():
        draft = FormDraft(CoreRoute(Screen.TASKS, day=DAY), "UTC", seed_title="T")
        state = DateChoice(
            draft.route, "UTC", draft, "due_at", START.replace(tzinfo=None), draft.expires_at
        )
        view = DatePickerView(controller.core, state)
        await choose(interaction, view, "picker_day", "31")  # only the second day menu contains 31
        interaction.edit_original_response.assert_not_awaited()
        assert draft.values()["due_at"] == "" and view.state == state

    asyncio.run(scenario())


def test_new_views_fit_legacy_limits_have_unique_ids_and_keep_expiry(controller):
    async def scenario():
        for screen in (Screen.PROJECTS, Screen.TASKS, Screen.CALENDAR):
            draft = FormDraft(CoreRoute(screen, day=DAY), "UTC", seed_title="*" * 250)
            draft.raw.update(name="*" * 200, title="*" * 250, description="*" * 4000)
            state = DateChoice(
                draft.route,
                "UTC",
                draft,
                "starts_at" if screen == Screen.CALENDAR else "due_at",
                START.replace(tzinfo=None),
                draft.expires_at,
            )
            views = [
                DraftView(controller.core, draft),
                DatePickerView(controller.core, state),
                DeadlineRangeView(controller.core, DeadlineRange(draft.route, "UTC")),
                DraftLinkView(controller.core, draft, Page((), 0, 0, 5)),
            ]
            for view in views:
                components = view.to_components()
                assert len(components) <= 5
                assert len({item.custom_id for item in view.children}) == len(view.children)
                for item in view.children:
                    assert len(item.custom_id) <= 100
                    if isinstance(item, discord.ui.Select):
                        assert len(item.options) <= 25
                        assert sum(option.default for option in item.options) <= 1
                assert all(
                    sum(5 if item["type"] == 3 else 1 for item in row["components"]) <= 5
                    for row in components
                )
            embed = render_draft(draft, link_name="*" * 250)
            assert len(embed) <= 6000 and all(len(field.value) <= 1024 for field in embed.fields)
            state = replace(state, expires_at=views[0].expires_at)
            next_view = DatePickerView(controller.core, state)
            assert next_view.expires_at <= views[0].expires_at
            modal = CoreFormModal(controller.core, views[0], draft, advanced=True)
            assert len(modal.children) <= 4

    asyncio.run(scenario())
