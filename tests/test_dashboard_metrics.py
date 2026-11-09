import asyncio
from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from app.db.models import CalendarEvent, Project, Task, User
from app.discord_bot.core_state import CoreRoute
from app.discord_bot.renderers.core import (
    confirmation_pages,
    render_confirmation,
    render_detail,
    render_today,
)
from app.discord_bot.renderers.dashboard import render_dashboard
from app.domain.approvals import ApprovalRequest
from app.domain.authorization import AuthorizationError
from app.domain.core import (
    EventData,
    EventRecord,
    Page,
    ProjectData,
    ProjectRecord,
    TaskData,
    TaskRecord,
)
from app.domain.modules import Screen
from app.services.core_management import SummaryService

START = datetime(2026, 10, 25, 13, tzinfo=UTC)
DAY = date(2026, 10, 25)


def test_dashboard_counts_and_today_are_real_and_owner_scoped(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await env.projects.create(env.owner, ProjectData(name="P"), request_id="p")
            task = await env.tasks.create(
                env.owner, TaskData(title="Due", due_at=START, priority="high"), request_id="t"
            )
            await env.tasks.set_status(env.owner, task.id, "done", expected=1)
            urgent = await env.tasks.create(
                env.owner, TaskData(title="Urgent", priority="critical"), request_id="u"
            )
            await env.calendar.create(
                env.owner,
                EventData(title="Today event", starts_at=START, ends_at=START + timedelta(hours=1)),
                request_id="e",
            )
            other = str(env.owner + 1)
            async with env.database.sessions.begin() as session:
                session.add(User(discord_user_id=other, timezone="UTC"))
                await session.flush()
                session.add_all(
                    [
                        Project(owner_id=other, name="Private"),
                        Task(owner_id=other, title="Private", status="todo", priority="critical"),
                        CalendarEvent(
                            owner_id=other,
                            title="Private",
                            starts_at=START,
                            ends_at=START + timedelta(hours=1),
                            status="confirmed",
                        ),
                        Task(owner_id=str(env.owner), title="Cancelled", status="cancelled"),
                        Project(owner_id=str(env.owner), name="Archived", status="archived"),
                    ]
                )
            counts = await dashboard.core.services.summary.counts(
                env.owner, DAY, "Asia/Ho_Chi_Minh"
            )
            assert counts == (2, 1, 1, 1)
            tasks, total = await dashboard.core.services.summary.today_tasks(
                env.owner, DAY, "Asia/Ho_Chi_Minh"
            )
            assert [row.id for row in tasks] == [urgent.id] and total == 1
            with patch("app.services.dashboard_service.datetime") as clock:
                clock.now.return_value = START
                overview = await dashboard.service.overview(env.owner)
            assert (
                overview.tasks,
                overview.projects,
                overview.done_tasks,
                overview.events_today,
            ) == (2, 1, 1, 1)
            fields = {item.name: item.value for item in render_dashboard(overview).fields}
            assert (
                fields["Tasks"] == "2"
                and fields["Projects"] == "1"
                and fields["Reminders"] == "Sắp ra mắt"
            )
            await dashboard.core.open(interaction, CoreRoute(Screen.TODAY, day=DAY))
            rendered = str(interaction.edit_original_response.await_args.kwargs["embed"].to_dict())
            assert "Today event" in rendered and "Urgent" in rendered and "Private" not in rendered
            interaction.message.edit.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("method", ["counts", "today_tasks"])
def test_summary_entries_deny_non_owner_before_session(authorization, method):
    sessions = Mock()
    with pytest.raises(AuthorizationError):
        asyncio.run(
            getattr(SummaryService(sessions, authorization), method)(
                authorization.owner_id + 1, DAY, "UTC"
            )
        )
    sessions.begin.assert_not_called()


def test_today_date_boundaries_use_owner_timezone(core_ui_factory):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            await env.calendar.create(
                env.owner,
                EventData(
                    title="Local midnight",
                    starts_at=datetime(2026, 10, 24, 17, tzinfo=UTC),
                    ends_at=datetime(2026, 10, 24, 18, tzinfo=UTC),
                ),
                request_id="midnight",
            )
            summary = dashboard.core.services.summary
            assert (await summary.counts(env.owner, DAY, "Asia/Ho_Chi_Minh"))[3] == 1
            assert (await summary.counts(env.owner, DAY, "UTC"))[3] == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["task", "project", "event"])
def test_core_embeds_escape_content_and_obey_limits(kind):
    common = {
        "id": "00000000-0000-0000-0000-000000000001",
        "owner_id": "123",
        "created_at": START,
        "updated_at": START,
    }
    if kind == "task":
        record = TaskRecord(
            **common, title="*" * 250, description="*" * 4000, version=1, completed_at=None
        )
        screen = Screen.TASKS
    elif kind == "project":
        record = ProjectRecord(**common, name="*" * 200, description="*" * 4000)
        screen = Screen.PROJECTS
    else:
        record = EventRecord(
            **common,
            title="@everyone " + "*" * 240,
            starts_at=START,
            ends_at=START + timedelta(hours=1),
            version=1,
            origin="manual",
        )
        screen = Screen.CALENDAR
    embed = render_detail(screen, record, "Asia/Ho_Chi_Minh")
    assert len(embed) <= 6000 and len(embed.description) <= 4096
    assert all(len(field.name) <= 256 and len(field.value) <= 1024 for field in embed.fields)
    assert "@everyone" not in str(embed.to_dict())


def test_long_confirmation_is_paginated_without_hiding_changes_or_tokens():
    before = TaskRecord(
        id="id",
        owner_id="123",
        title="T",
        description="*" * 4000,
        version=1,
        completed_at=None,
        created_at=START,
        updated_at=START,
    )
    after = TaskData(title="T", description="_" * 4000, status="cancelled")
    request = ApprovalRequest(
        "never-display-token", "cancel_task", START + timedelta(minutes=5), before, after, ()
    )
    pages = confirmation_pages(request, "Asia/Ho_Chi_Minh", {})
    assert len(pages) > 1 and sum(len(page) for page in pages) > 16000
    for index in range(len(pages)):
        embed = render_confirmation(request, pages, index)
        assert len(embed) < 6000 and len(embed.description) <= 4096
        assert request.token not in str(embed.to_dict())


def test_today_preview_obeys_field_limits_for_long_titles_and_many_items():
    records = tuple(
        EventRecord(
            id=str(index),
            owner_id="123",
            title="*" * 250,
            starts_at=START,
            ends_at=START + timedelta(hours=1),
            version=1,
            origin="manual",
            created_at=START,
            updated_at=START,
        )
        for index in range(5)
    )
    embed = render_today(DAY, "Asia/Ho_Chi_Minh", Page(records, 20, 0, 5), (), 0)
    assert all(len(field.value) <= 1024 for field in embed.fields)
    assert len(embed) < 6000
