import asyncio
from datetime import UTC, date, datetime, timedelta

import discord
import pytest

from app.discord_bot.core_state import CoreRoute
from app.discord_bot.views.core import ConfirmationView, CoreErrorView, CorePanelView, LinkView
from app.discord_bot.views.core_pickers import DraftView
from app.domain.core import EventData, ProjectData, TaskData
from app.domain.modules import Screen

DAY = date(2026, 10, 25)
START = datetime(2026, 10, 25, 13, tzinfo=UTC)


def fresh(interaction):
    interaction.response.is_done.return_value = False


def view_of(interaction):
    return interaction.edit_original_response.await_args.kwargs["view"]


async def press(interaction, view, label):
    fresh(interaction)
    await next(item for item in view.children if getattr(item, "label", None) == label).callback(
        interaction
    )


async def choose(interaction, view, action, value):
    fresh(interaction)
    select = next(item for item in view.children if getattr(item, "action", None) == action)
    select._values = [value]
    await select.callback(interaction)


async def submit(interaction, modal, *, save=True, **values):
    # Existing CRUD cases supply already-selected dates; picker callbacks have their own tests.
    if "is_fixed" in values:
        modal.draft.selections["is_fixed"] = values.pop("is_fixed") == "có"
    modal.draft.raw.update({key: value for key, value in values.items() if key not in modal.inputs})
    for key, item in modal.inputs.items():
        item._value = values.get(key, item.default or "")
    fresh(interaction)
    await modal.on_submit(interaction)
    current = view_of(interaction)
    if save and isinstance(current, DraftView) and not current.is_finished():
        await press(interaction, current, "Lưu")


async def add(interaction, view, **values):
    await press(interaction, view, "Thêm")
    modal = interaction.response.send_modal.await_args.args[0]
    await submit(interaction, modal, **values)
    return view_of(interaction)


def test_project_task_event_creation_edit_status_and_links_through_ui(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await dashboard.navigate(interaction, Screen.PROJECTS, new_panel=True)
            project_view = await add(
                interaction,
                view_of(interaction),
                name="HRM",
                description="Project notes",
                deadline_at="2026-10-25 20:00",
            )
            assert isinstance(project_view, CorePanelView)
            project = project_view.record
            assert project.deadline_at == START
            await press(interaction, project_view, "Thêm task")
            modal = interaction.response.send_modal.await_args.args[0]
            assert len(modal.children) <= 5
            await submit(
                interaction,
                modal,
                title="Học Docker",
                description="Task notes",
                due_at="2026-10-25 20:00",
                estimated_minutes="45",
            )
            task_view = view_of(interaction)
            task = task_view.record
            assert task.project_id == project.id and task.due_at == START
            assert task_view.route.parent.project_id == project.id
            await choose(interaction, task_view, "priority", "critical")
            task_view = view_of(interaction)
            assert (
                task_view.record.priority == "critical"
                and task_view.record.description == "Task notes"
            )
            await press(interaction, task_view, "Hoàn thành")
            task_view = view_of(interaction)
            completed = task_view.record.completed_at
            assert completed is not None
            assert (await env.projects.progress(env.owner, project.id)).percent == 100
            await press(interaction, task_view, "Sửa")
            modal = interaction.response.send_modal.await_args.args[0]
            await submit(interaction, modal, title="Docker edited", due_at="")
            task_view = view_of(interaction)
            assert task_view.record.status == "done"
            assert task_view.record.completed_at == completed
            assert task_view.record.due_at is None and task_view.record.project_id == project.id
            assert (
                task_view.record.priority == "critical" and task_view.record.estimated_minutes == 45
            )
            await press(interaction, task_view, "Mở lại")
            task_view = view_of(interaction)
            assert task_view.record.status == "todo" and task_view.record.completed_at is None
            await press(interaction, task_view, "Lên lịch")
            modal = interaction.response.send_modal.await_args.args[0]
            assert modal.inputs["title"].default == "Docker edited"
            await submit(
                interaction,
                modal,
                starts_at="2026-10-25 20:00",
                ends_at="2026-10-25 21:00",
                is_fixed="có",
            )
            event = view_of(interaction).record
            assert event.task_id == task.id and event.starts_at == START and event.is_fixed
            assert view_of(interaction).route.parent.day == DAY
            interaction.message.edit.assert_not_awaited()
            assert (
                "Đã lưu"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )

    asyncio.run(scenario())


def test_real_lists_paging_filters_project_and_deadline_picker(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            project = await env.projects.create(env.owner, ProjectData(name="P"), request_id="p")
            for index in range(7):
                await env.tasks.create(
                    env.owner,
                    TaskData(
                        title=f"Task {index}",
                        priority="high" if index < 3 else "low",
                        project_id=project.id if index < 4 else None,
                        due_at=START + timedelta(days=index),
                    ),
                    request_id=str(index),
                )
            await dashboard.navigate(interaction, Screen.TASKS, new_panel=True)
            first = view_of(interaction)
            assert (
                len(
                    next(
                        item for item in first.children if getattr(item, "action", None) == "record"
                    ).options
                )
                == 5
            )
            await press(interaction, first, "Next")
            second = view_of(interaction)
            assert (
                "Trang 2/2"
                in interaction.edit_original_response.await_args.kwargs["embed"].footer.text
            )
            assert first.is_finished()
            await press(interaction, second, "Dự án")
            picker = view_of(interaction)
            assert isinstance(picker, LinkView)
            await choose(interaction, picker, "link", project.id)
            current = view_of(interaction)
            assert current.route.project_id == project.id and current.route.page == 0
            await choose(interaction, current, "filter_priority", "high")
            current = view_of(interaction)
            assert (
                "3 bản ghi"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            await press(interaction, current, "Deadline")
            for label in ("Từ ngày", "Đến hết ngày"):
                await press(interaction, view_of(interaction), label)
                await choose(interaction, view_of(interaction), "picker_day_late", "26")
                await press(interaction, view_of(interaction), "Dùng ngày")
            await press(interaction, view_of(interaction), "Áp dụng")
            current = view_of(interaction)
            assert (
                "1 bản ghi"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            select = next(
                item for item in current.children if getattr(item, "action", None) == "record"
            )
            await choose(interaction, current, "record", select.options[0].value)
            detail = view_of(interaction)
            assert detail.record.title == "Task 1"
            await press(interaction, detail, "Back")
            assert view_of(interaction).route == current.route

    asyncio.run(scenario())


def test_link_pickers_change_and_clear_relationship_without_copying_ids(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            project = await env.projects.create(env.owner, ProjectData(name="P"), request_id="p")
            task = await env.tasks.create(env.owner, TaskData(title="T"), request_id="t")
            await dashboard.core.open(interaction, CoreRoute(Screen.TASKS, item_id=task.id))
            await press(interaction, view_of(interaction), "Đổi dự án")
            await choose(interaction, view_of(interaction), "link", project.id)
            assert view_of(interaction).record.project_id == project.id
            await press(interaction, view_of(interaction), "Đổi dự án")
            await choose(interaction, view_of(interaction), "link", "none")
            assert view_of(interaction).record.project_id is None
            event = await env.calendar.create(
                env.owner,
                EventData(title="E", starts_at=START, ends_at=START + timedelta(hours=1)),
                request_id="e",
            )
            await dashboard.core.open(interaction, CoreRoute(Screen.CALENDAR, item_id=event.id))
            await press(interaction, view_of(interaction), "Đổi task")
            await choose(interaction, view_of(interaction), "link", task.id)
            confirm = view_of(interaction)
            assert isinstance(confirm, ConfirmationView)
            assert (await env.calendar.get(env.owner, event.id)).task_id is None
            await press(interaction, confirm, "Duyệt")
            assert view_of(interaction).record.task_id == task.id

    asyncio.run(scenario())


def test_overlap_can_be_rejected_then_explicitly_approved_without_duplicate(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            original = await env.calendar.create(
                env.owner,
                EventData(title="Original", starts_at=START, ends_at=START + timedelta(hours=1)),
                request_id="one",
            )
            route = CoreRoute(Screen.CALENDAR, day=DAY)
            await dashboard.core.open(interaction, route)
            pending = await add(
                interaction,
                view_of(interaction),
                title="Overlap",
                starts_at="2026-10-25 20:30",
                ends_at="2026-10-25 21:30",
            )
            assert isinstance(pending, ConfirmationView)
            assert "Original" in "\n".join(pending.text_pages)
            assert (await env.calendar.list_day(env.owner, DAY)).total == 1
            await press(interaction, pending, "Bỏ qua")
            assert (await env.calendar.list_day(env.owner, DAY)).total == 1
            pending = await add(
                interaction,
                view_of(interaction),
                title="Overlap",
                starts_at="2026-10-25 20:30",
                ends_at="2026-10-25 21:30",
            )
            await press(interaction, pending, "Duyệt")
            assert (await env.calendar.list_day(env.owner, DAY)).total == 2
            await press(interaction, pending, "Duyệt")
            assert (await env.calendar.list_day(env.owner, DAY)).total == 2
            assert await env.calendar.get(env.owner, original.id) == original

    asyncio.run(scenario())


@pytest.mark.parametrize("action,value", [("status", "cancelled"), ("fixed", "yes")])
def test_confirmed_event_changes_require_explicit_approval(
    core_ui_factory, interaction, action, value
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            event = await env.calendar.create(
                env.owner,
                EventData(title="E", starts_at=START, ends_at=START + timedelta(hours=1)),
                request_id="e",
            )
            await dashboard.core.open(interaction, CoreRoute(Screen.CALENDAR, item_id=event.id))
            await choose(interaction, view_of(interaction), action, value)
            pending = view_of(interaction)
            assert isinstance(pending, ConfirmationView)
            assert await env.calendar.get(env.owner, event.id) == event
            await press(interaction, pending, "Duyệt")
            assert view_of(interaction).record.version == 2

    asyncio.run(scenario())


def test_project_archive_and_task_cancel_do_not_execute_when_skipped(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            project = await env.projects.create(env.owner, ProjectData(name="P"), request_id="p")
            task = await env.tasks.create(
                env.owner, TaskData(title="T", project_id=project.id), request_id="t"
            )
            for screen, row, status in (
                (Screen.PROJECTS, project, "archived"),
                (Screen.TASKS, task, "cancelled"),
            ):
                await dashboard.core.open(interaction, CoreRoute(screen, item_id=row.id))
                await choose(interaction, view_of(interaction), "status", status)
                await press(interaction, view_of(interaction), "Bỏ qua")
                assert (
                    await dashboard.core.service(screen).get(env.owner, row.id)
                ).status == row.status
            assert (await env.tasks.get(env.owner, task.id)).project_id == project.id

    asyncio.run(scenario())


def test_calendar_date_week_and_adjacent_events_use_local_timezone(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await env.calendar.create(
                env.owner,
                EventData(title="E", starts_at=START, ends_at=START + timedelta(hours=1)),
                request_id="one",
            )
            await dashboard.core.open(interaction, CoreRoute(Screen.CALENDAR, day=DAY))
            detail = await add(
                interaction,
                view_of(interaction),
                title="Adjacent",
                starts_at="2026-10-25 21:00",
                ends_at="2026-10-25 22:00",
            )
            assert not isinstance(detail, ConfirmationView)
            await press(interaction, detail, "Back")
            await press(interaction, view_of(interaction), "Xem tuần")
            assert view_of(interaction).route.weekly
            await press(interaction, view_of(interaction), "Chọn ngày")
            await choose(interaction, view_of(interaction), "picker_day_late", "26")
            await press(interaction, view_of(interaction), "Dùng ngày")
            assert view_of(interaction).route.day == date(2026, 10, 26)
            assert view_of(interaction).route.weekly

    asyncio.run(scenario())


def test_stale_modal_and_forged_select_fail_without_overwriting_data(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            task = await env.tasks.create(env.owner, TaskData(title="Old"), request_id="t")
            await dashboard.core.open(interaction, CoreRoute(Screen.TASKS, item_id=task.id))
            await press(interaction, view_of(interaction), "Sửa")
            modal = interaction.response.send_modal.await_args.args[0]
            await env.tasks.update(
                env.owner, task.id, TaskData(title="External change"), expected=1
            )
            await submit(interaction, modal, title="Stale edit")
            assert isinstance(view_of(interaction), CoreErrorView)
            assert (
                "đã thay đổi"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            assert (await env.tasks.get(env.owner, task.id)).title == "External change"
            await press(interaction, view_of(interaction), "Refresh")
            current = view_of(interaction)
            calls = interaction.edit_original_response.await_count
            await choose(interaction, current, "status", "admin")
            assert interaction.edit_original_response.await_count == calls
            assert (await env.tasks.get(env.owner, task.id)).version == 2

    asyncio.run(scenario())


def test_validation_keeps_form_values_for_correction_and_empty_state_is_actionable(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await dashboard.core.open(interaction, CoreRoute(Screen.TASKS))
            assert "Chưa có bản ghi" in str(
                interaction.edit_original_response.await_args.kwargs["embed"].to_dict()
            )
            await press(interaction, view_of(interaction), "Thêm")
            modal = interaction.response.send_modal.await_args.args[0]
            await submit(
                interaction, modal, title="Keep this", due_at="10/11", estimated_minutes="-5"
            )
            error_view = view_of(interaction)
            assert isinstance(error_view, CoreErrorView)
            assert (await env.tasks.list(env.owner)).total == 0
            await press(interaction, error_view, "Nhập lại")
            retry = interaction.response.send_modal.await_args.args[0]
            assert retry.inputs["title"].default == "Keep this"
            assert retry.draft.request_id == modal.draft.request_id
            await submit(interaction, retry, due_at="2026-10-25 20:00", estimated_minutes="30")
            assert view_of(interaction).record.title == "Keep this"
            assert (await env.tasks.list(env.owner)).total == 1

    asyncio.run(scenario())


def test_saved_record_is_not_resubmitted_when_discord_render_fails(
    core_ui_factory, interaction, monkeypatch
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await dashboard.core.open(interaction, CoreRoute(Screen.TASKS))
            await press(interaction, view_of(interaction), "Thêm")
            modal = interaction.response.send_modal.await_args.args[0]
            await submit(interaction, modal, title="Saved once", save=False)
            draft_view = view_of(interaction)
            error = discord.NotFound(
                type("Response", (), {"status": 404, "reason": "test"})(), "private HTTP payload"
            )
            interaction.edit_original_response.side_effect = error
            await press(interaction, draft_view, "Lưu")
            assert draft_view.draft.intent.saved is not None
            assert (await env.tasks.list(env.owner)).total == 1
            assert "Đã lưu" in interaction.followup.send.await_args.args[0]
            interaction.edit_original_response.side_effect = None
            await press(interaction, draft_view, "Lưu")
            assert (await env.tasks.list(env.owner)).total == 1

    asyncio.run(scenario())


def test_duplicate_modal_submissions_create_one_record(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await dashboard.core.open(interaction, CoreRoute(Screen.TASKS))
            await press(interaction, view_of(interaction), "Thêm")
            modal = interaction.response.send_modal.await_args.args[0]
            await asyncio.gather(
                submit(interaction, modal, title="Once"), submit(interaction, modal, title="Once")
            )
            assert (await env.tasks.list(env.owner)).total == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("screen", [Screen.TASKS, Screen.PROJECTS, Screen.CALENDAR, Screen.TODAY])
def test_ready_modules_render_real_empty_state_not_placeholder(
    core_ui_factory, interaction, screen
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await dashboard.core.open(interaction, CoreRoute(screen, day=DAY))
            view = view_of(interaction)
            embed = interaction.edit_original_response.await_args.kwargs["embed"]
            assert isinstance(view, CorePanelView)
            assert "Sắp ra mắt" not in str(embed.to_dict())
            assert "Chưa có" in str(embed.to_dict())
            assert len(view.to_components()) <= 5

    asyncio.run(scenario())


@pytest.mark.parametrize("screen", [Screen.PROJECTS, Screen.CALENDAR])
def test_project_and_event_edit_keep_untouched_fields(core_ui_factory, interaction, screen):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            if screen == Screen.PROJECTS:
                row = await env.projects.create(
                    env.owner,
                    ProjectData(
                        name="Original", description="Keep", status="paused", deadline_at=START
                    ),
                    request_id="p",
                )
            else:
                task = await env.tasks.create(env.owner, TaskData(title="Linked"), request_id="t")
                row = await env.calendar.create(
                    env.owner,
                    EventData(
                        title="Original",
                        starts_at=START,
                        ends_at=START + timedelta(hours=1),
                        is_fixed=True,
                        task_id=task.id,
                    ),
                    request_id="e",
                )
            await dashboard.core.open(interaction, CoreRoute(screen, item_id=row.id))
            await press(interaction, view_of(interaction), "Sửa")
            modal = interaction.response.send_modal.await_args.args[0]
            await submit(
                interaction, modal, **{"name" if screen == Screen.PROJECTS else "title": "Edited"}
            )
            if screen == Screen.CALENDAR:
                pending = view_of(interaction)
                assert isinstance(pending, ConfirmationView)
                assert "Original" in "\n".join(pending.text_pages) and "Edited" in "\n".join(
                    pending.text_pages
                )
                await press(interaction, pending, "Duyệt")
            saved = view_of(interaction).record
            if screen == Screen.PROJECTS:
                assert (
                    saved.description == "Keep"
                    and saved.status == "paused"
                    and saved.deadline_at == START
                )
            else:
                assert saved.is_fixed and saved.task_id == task.id
                assert saved.starts_at == START and saved.ends_at == START + timedelta(hours=1)

    asyncio.run(scenario())


def test_approval_requires_review_again_when_new_conflict_appears(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            from app.db.models import CalendarEvent

            await env.calendar.create(
                env.owner,
                EventData(title="First", starts_at=START, ends_at=START + timedelta(hours=1)),
                request_id="first",
            )
            await dashboard.core.open(interaction, CoreRoute(Screen.CALENDAR, day=DAY))
            pending = await add(
                interaction,
                view_of(interaction),
                title="Pending",
                starts_at="2026-10-25 20:30",
                ends_at="2026-10-25 21:30",
            )
            async with env.database.sessions.begin() as session:
                session.add(
                    CalendarEvent(
                        owner_id=str(env.owner),
                        title="New confirmed conflict",
                        starts_at=START,
                        ends_at=START + timedelta(hours=1),
                        status="confirmed",
                    )
                )
            await press(interaction, pending, "Duyệt")
            assert isinstance(view_of(interaction), CoreErrorView)
            assert (await env.calendar.list_day(env.owner, DAY)).total == 2
            assert not any(
                getattr(item, "label", None) == "Thử lại" for item in view_of(interaction).children
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("forged_early_approve", [True, False])
def test_many_conflicts_have_pages_and_approve_only_on_last(
    core_ui_factory, interaction, forged_early_approve
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            from app.db.models import CalendarEvent

            async with env.database.sessions.begin() as session:
                session.add_all(
                    [
                        CalendarEvent(
                            owner_id=str(env.owner),
                            title=f"Conflict {index} " + "*" * 230,
                            starts_at=START,
                            ends_at=START + timedelta(hours=1),
                            status="confirmed",
                        )
                        for index in range(15)
                    ]
                )
            await dashboard.core.open(interaction, CoreRoute(Screen.CALENDAR, day=DAY))
            pending = await add(
                interaction,
                view_of(interaction),
                title="New",
                starts_at="2026-10-25 20:00",
                ends_at="2026-10-25 21:00",
            )
            assert len(pending.text_pages) > 1
            assert next(
                item for item in pending.children if getattr(item, "action", None) == "approve"
            ).disabled
            assert all(pending.request.token not in item.custom_id for item in pending.children)
            if forged_early_approve:
                await press(interaction, pending, "Duyệt")
                assert (await env.calendar.list_day(env.owner, DAY)).total == 15
                return
            while pending.confirm_page < len(pending.text_pages) - 1:
                await press(interaction, pending, "Next")
                pending = view_of(interaction)
                assert len(interaction.edit_original_response.await_args.kwargs["embed"]) < 6000
            assert not next(
                item for item in pending.children if getattr(item, "action", None) == "approve"
            ).disabled
            await press(interaction, pending, "Duyệt")
            assert (await env.calendar.list_day(env.owner, DAY)).total == 16

    asyncio.run(scenario())


def test_restart_restores_old_anchor_buttons_and_renders_persisted_tasks(
    core_ui_factory, settings, interaction
):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            from unittest.mock import AsyncMock, patch

            from app.db.session import Database
            from app.discord_bot.client import NovaClient
            from app.domain.schemas import DashboardLocation

            await env.tasks.create(
                env.owner, TaskData(title="Persisted through restart"), request_id="persistent"
            )
            await dashboard.settings.save_dashboard(
                env.owner, DashboardLocation(interaction.channel_id, interaction.message.id)
            )
            first = NovaClient(settings, env.database)
            with patch.object(first.tree, "sync", new=AsyncMock(return_value=[])):
                await first.setup_hook()
            ids = [item.custom_id for item in first.persistent_views[0].children]
            await first.close()
            second = NovaClient(settings, Database(settings.database_url))
            try:
                with patch.object(second.tree, "sync", new=AsyncMock(return_value=[])):
                    await second.setup_hook()
                root = second.persistent_views[0]
                assert [item.custom_id for item in root.children] == ids
                fresh(interaction)
                await next(
                    item for item in root.children if getattr(item, "screen", None) == Screen.TASKS
                ).callback(interaction)
                assert "Persisted through restart" in str(
                    interaction.edit_original_response.await_args.kwargs["embed"].to_dict()
                )
                assert isinstance(view_of(interaction), CorePanelView)
                interaction.message.edit.assert_not_awaited()
            finally:
                await second.close()

    asyncio.run(scenario())
