import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.approvals import ApprovalStore
from app.domain.core import EventData, TaskData, to_record
from app.domain.errors import (
    ApprovalInvalidError,
    CalendarConflictError,
    ConfirmationRequired,
    StaleWriteError,
)

START = datetime(2026, 10, 25, 13, tzinfo=UTC)


def event_data(**changes):
    return EventData(
        **{"title": "E", "starts_at": START, "ends_at": START + timedelta(hours=1), **changes}
    )


def test_overlap_requires_explicit_bound_approval_then_creates_once(core_factory):
    async def scenario():
        async with core_factory() as env:
            first = await env.calendar.create(env.owner, event_data(), request_id="first")
            data = event_data(title="Overlap", starts_at=START + timedelta(minutes=30))
            with pytest.raises(CalendarConflictError) as pending:
                await env.calendar.create(env.owner, data, request_id="second")
            request = pending.value.request
            assert request.reason == "overlap" and [row.id for row in request.conflicts] == [
                first.id
            ]
            assert (
                await env.calendar.list(env.owner, START, START + timedelta(hours=2))
            ).total == 1
            with pytest.raises(ApprovalInvalidError):
                await env.calendar.create(
                    env.owner,
                    replace(data, title="Tampered"),
                    request_id="second",
                    approval_token=request.token,
                )
            created = await env.calendar.create(
                env.owner, data, request_id="second", approval_token=request.token
            )
            repeated = await env.calendar.create(
                env.owner, data, request_id="second", approval_token=request.token
            )
            assert created.id == repeated.id
            assert (
                await env.calendar.list(env.owner, START, START + timedelta(hours=2))
            ).total == 2
            assert (await env.calendar.get(env.owner, first.id)) == first

    asyncio.run(scenario())


def test_half_open_boundary_proposed_and_cancelled_events_are_not_conflicts(core_factory):
    async def scenario():
        async with core_factory() as env:
            first = await env.calendar.create(env.owner, event_data(), request_id="first")
            await env.calendar.create(
                env.owner,
                event_data(starts_at=first.ends_at, ends_at=first.ends_at + timedelta(hours=1)),
                request_id="adjacent",
            )
            proposed = await env.calendar.create(
                env.owner, event_data(status="proposed"), request_id="proposed"
            )
            assert proposed.status == "proposed"
            with pytest.raises(ConfirmationRequired) as pending:
                await env.calendar.cancel(env.owner, first.id, expected=first.version)
            await env.calendar.cancel(
                env.owner,
                first.id,
                expected=first.version,
                approval_token=pending.value.request.token,
            )
            created = await env.calendar.create(env.owner, event_data(), request_id="new")
            assert created.status == "confirmed"

    asyncio.run(scenario())


def test_confirmed_update_is_protected_excludes_self_and_rechecks_conflicts(core_factory):
    async def scenario():
        async with core_factory() as env:
            first = await env.calendar.create(
                env.owner, event_data(is_fixed=True), request_id="first"
            )
            data = replace(
                to_record(EventData, first),
                title="Edited",
                ends_at=first.ends_at + timedelta(minutes=15),
            )
            with pytest.raises(ConfirmationRequired) as pending:
                await env.calendar.update(env.owner, first.id, data, expected=first.version)
            assert pending.value.request.conflicts == ()
            assert (await env.calendar.get(env.owner, first.id)).title == first.title
            await env.calendar.create(
                env.owner,
                event_data(
                    starts_at=first.ends_at + timedelta(minutes=5),
                    ends_at=first.ends_at + timedelta(hours=1),
                ),
                request_id="new-conflict",
            )
            with pytest.raises(ApprovalInvalidError):
                await env.calendar.update(
                    env.owner,
                    first.id,
                    data,
                    expected=first.version,
                    approval_token=pending.value.request.token,
                )
            with pytest.raises(CalendarConflictError) as fresh:
                await env.calendar.update(env.owner, first.id, data, expected=first.version)
            updated = await env.calendar.update(
                env.owner,
                first.id,
                data,
                expected=first.version,
                approval_token=fresh.value.request.token,
            )
            assert updated.title == "Edited" and updated.version == 2 and updated.is_fixed is True
            with pytest.raises(StaleWriteError):
                await env.calendar.update(
                    env.owner,
                    first.id,
                    data,
                    expected=first.version,
                    approval_token=fresh.value.request.token,
                )

    asyncio.run(scenario())


def test_conflict_disappearing_invalidates_old_approval_instead_of_silently_reusing_it(
    core_factory,
):
    async def scenario():
        async with core_factory() as env:
            first = await env.calendar.create(env.owner, event_data(), request_id="first")
            with pytest.raises(CalendarConflictError) as pending:
                await env.calendar.create(env.owner, event_data(), request_id="second")
            token = pending.value.request.token
            with pytest.raises(ConfirmationRequired) as cancel:
                await env.calendar.cancel(env.owner, first.id, expected=1)
            await env.calendar.cancel(
                env.owner, first.id, expected=1, approval_token=cancel.value.request.token
            )
            with pytest.raises(ApprovalInvalidError):
                await env.calendar.create(
                    env.owner, event_data(), request_id="second", approval_token=token
                )
            assert (
                await env.calendar.create(env.owner, event_data(), request_id="second")
            ).status == "confirmed"

    asyncio.run(scenario())


def test_approval_expiry_wrong_token_and_restart_do_not_change_data(core_factory):
    async def scenario():
        now = [START]
        store = ApprovalStore(clock=lambda: now[0])
        async with core_factory(approvals=store) as env:
            task = await env.tasks.create(env.owner, TaskData(title="T"), request_id="t")
            with pytest.raises(ConfirmationRequired) as pending:
                await env.tasks.set_status(env.owner, task.id, "cancelled", expected=1)
            token = pending.value.request.token
            now[0] += timedelta(minutes=5)
            with pytest.raises(ApprovalInvalidError):
                await env.tasks.set_status(
                    env.owner, task.id, "cancelled", expected=1, approval_token=token
                )
            with pytest.raises(ApprovalInvalidError):
                await env.tasks.set_status(
                    env.owner, task.id, "cancelled", expected=1, approval_token="forged"
                )
            recreated = type(env.tasks)(env.database.sessions, env.tasks.authorization)
            with pytest.raises(ApprovalInvalidError):
                await recreated.set_status(
                    env.owner, task.id, "cancelled", expected=1, approval_token=token
                )
            assert (await env.tasks.get(env.owner, task.id)).status == "todo"

    asyncio.run(scenario())


def test_concurrent_calendar_creation_rechecks_overlap_before_second_commit(core_factory):
    async def scenario():
        async with core_factory() as env:
            results = await asyncio.gather(
                *(
                    env.calendar.create(env.owner, event_data(), request_id=f"event-{index}")
                    for index in range(2)
                ),
                return_exceptions=True,
            )
            assert sum(isinstance(result, CalendarConflictError) for result in results) == 1
            assert (
                await env.calendar.list(env.owner, START, START + timedelta(hours=1))
            ).total == 1

    asyncio.run(scenario())


def test_local_day_week_timeline_order_and_timezone_round_trip(core_factory):
    async def scenario():
        async with core_factory() as env:
            # Create later event first: timeline must still sort by starts_at.
            late = await env.calendar.create(
                env.owner,
                event_data(
                    starts_at=START + timedelta(hours=2), ends_at=START + timedelta(hours=3)
                ),
                request_id="late",
            )
            early = await env.calendar.create(env.owner, event_data(), request_id="early")
            crossing = await env.calendar.create(
                env.owner,
                event_data(
                    starts_at=datetime(2026, 10, 24, 16, 30, tzinfo=UTC),
                    ends_at=datetime(2026, 10, 24, 17, 30, tzinfo=UTC),
                ),
                request_id="midnight",
            )
            day = await env.calendar.list_day(env.owner, date(2026, 10, 25))
            assert [row.id for row in day.items] == [crossing.id, early.id, late.id]
            utc_day = await env.calendar.list_day(env.owner, date(2026, 10, 25), timezone="UTC")
            assert [row.id for row in utc_day.items] == [early.id, late.id]
            week = await env.calendar.list_week(env.owner, date(2026, 10, 25))
            assert week.total == 3
            assert (await env.calendar.list_week(env.owner, date(2026, 11, 1))).total == 0

    asyncio.run(scenario())
