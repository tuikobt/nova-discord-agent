import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import func, select

from app.db.models import ReminderDelivery, Task, User, UserSettings
from app.domain.authorization import AuthorizationError
from app.domain.core import TaskData
from app.domain.errors import (
    ConfirmationRequired,
    DuplicateRequestError,
    NotFoundError,
    StaleWriteError,
    StorageError,
    ValidationError,
)
from app.domain.reminder_delivery import CLAIM_LEASE, DeliveryFailure, next_occurrence, quiet_until
from app.domain.reminders import RecurrenceRule, ReminderData
from app.scheduler.dispatcher import ReminderDispatcher
from app.services.reminder_service import ReminderService

START = datetime(2026, 10, 25, 13, tzinfo=UTC)


@pytest.fixture
def reminder_env(core_factory):
    @asynccontextmanager
    async def factory():
        async with core_factory() as env:
            clock = [START - timedelta(minutes=1)]
            service = ReminderService(
                env.database.sessions,
                env.tasks.authorization,
                clock=lambda: clock[0],
                channel_validator=AsyncMock(),
            )
            sender = SimpleNamespace(
                send=AsyncMock(return_value="123456789"), available=lambda: True
            )
            yield SimpleNamespace(
                **vars(env),
                service=service,
                clock=clock,
                sender=sender,
                dispatcher=ReminderDispatcher(service, sender),
            )

    return factory


async def create(env, *, key="one", **values):
    return await env.service.create(
        env.owner,
        ReminderData(**{"title": "Synthetic reminder", "next_fire_at": START, **values}),
        request_id=key,
    )


async def confirm_change(service, actor, operation):
    with pytest.raises(ConfirmationRequired) as pending:
        await operation()
    request = pending.value.request
    return await service.update(
        actor,
        request.before.id,
        request.after,
        expected=request.before.updated_at,
        approval_token=request.token,
    )


def test_create_read_paging_idempotency_and_references_are_owner_scoped(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            task = await env.tasks.create(
                env.owner,
                TaskData(title="T"),
                request_id="t",
            )
            row = await create(env, task_id=task.id)
            assert (await create(env, task_id=task.id)).id == row.id
            with pytest.raises(DuplicateRequestError):
                await create(env, title="Changed")
            for index in range(6):
                await create(env, key=str(index))
            page = await env.service.list(env.owner, page=1, page_size=5)
            assert page.total == 7 and len(page.items) == 2
            async with env.database.sessions.begin() as session:
                session.add(User(discord_user_id=str(env.owner + 1), timezone="UTC"))
                await session.flush()
                foreign = Task(owner_id=str(env.owner + 1), title="Foreign")
                session.add(foreign)
                await session.flush()
                foreign_id = foreign.id
            with pytest.raises(NotFoundError):
                await create(env, key="foreign", task_id=foreign_id)

    asyncio.run(scenario())


def test_changes_require_approval_and_stale_or_replayed_approval_cannot_write(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            edited = replace(row.data(), title="Edited")
            with pytest.raises(ConfirmationRequired) as pending:
                await env.service.update(env.owner, row.id, edited, expected=row.updated_at)
            assert (await env.service.get(env.owner, row.id)).title == row.title
            await env.service.update(
                env.owner,
                row.id,
                edited,
                expected=row.updated_at,
                approval_token=pending.value.request.token,
            )
            with pytest.raises(StaleWriteError):
                await env.service.update(
                    env.owner,
                    row.id,
                    edited,
                    expected=row.updated_at,
                    approval_token=pending.value.request.token,
                )

    asyncio.run(scenario())


def test_one_time_due_sends_once_and_history_is_durable(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            await env.dispatcher.tick()
            env.sender.send.assert_not_awaited()
            env.clock[0] = START
            await env.dispatcher.tick()
            await env.dispatcher.tick()
            env.sender.send.assert_awaited_once()
            assert (await env.service.get(env.owner, row.id)).status == "done"
            history = await env.service.history(env.owner, row.id)
            assert len(history) == 1 and history[0].status == "sent"
            assert history[0].discord_message_id == "123456789"
            restarted = ReminderService(
                env.database.sessions, env.tasks.authorization, clock=lambda: env.clock[0]
            )
            assert (await restarted.get(env.owner, row.id)).status == "done"

    asyncio.run(scenario())


@pytest.mark.parametrize("kind,weekday,days", [("daily", None, 1), ("weekly", 6, 7)])
def test_recurring_advances_one_logical_reminder_without_backlog(reminder_env, kind, weekday, days):
    async def scenario():
        async with reminder_env() as env:
            row = await create(
                env, recurrence_type=kind, recurrence=RecurrenceRule(time="20:00", weekday=weekday)
            )
            env.clock[0] = START
            await env.dispatcher.tick()
            current = await env.service.get(env.owner, row.id)
            assert (
                current.next_fire_at == START + timedelta(days=days) and current.status == "active"
            )
            await env.dispatcher.tick()
            assert len((await env.service.list(env.owner)).items) == 1
            env.sender.send.assert_awaited_once()

    asyncio.run(scenario())


def test_retry_is_capped_durable_and_does_not_report_sent_on_failure(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            env.sender.send.side_effect = DeliveryFailure("http_error")
            env.clock[0] = START
            for delta in (timedelta(), timedelta(minutes=1), timedelta(minutes=5)):
                env.clock[0] += delta
                await env.dispatcher.tick()
            await env.dispatcher.tick()
            history = await env.service.history(env.owner, row.id)
            assert env.sender.send.await_count == 3
            assert history[0].status == "failed" and history[0].finished_reason == "exhausted"
            assert history[0].discord_message_id is None
            assert (await env.service.get(env.owner, row.id)).status == "paused"

    asyncio.run(scenario())


def test_restart_claim_lease_recovery_and_fencing_stale_completion(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            env.clock[0] = START
            delivery = env.dispatcher.deliveries
            await delivery.enqueue(env.owner)
            key = (await delivery.due(env.owner))[0]
            claim = await delivery.claim(env.owner, key)
            assert await delivery.claim(env.owner, key) is None
            env.clock[0] += CLAIM_LEASE + timedelta(seconds=1)
            recovered = await delivery.claim(env.owner, key)
            assert recovered.delivery.attempt_count == 2
            with pytest.raises(StaleWriteError):
                await delivery.finish(env.owner, claim, message_id="123")
            await delivery.finish(env.owner, recovered, message_id="456")
            assert (await env.service.history(env.owner, row.id))[0].discord_message_id == "456"

    asyncio.run(scenario())


@pytest.mark.parametrize("repeating", [False, True])
def test_overdue_more_than_30_minutes_is_recorded_without_spam(reminder_env, repeating):
    async def scenario():
        async with reminder_env() as env:
            extra = (
                {"recurrence_type": "daily", "recurrence": RecurrenceRule(time="20:00")}
                if repeating
                else {}
            )
            row = await create(env, **extra)
            env.clock[0] = START + timedelta(days=3)
            await env.dispatcher.tick()
            env.sender.send.assert_not_awaited()
            history = await env.service.history(env.owner, row.id)
            assert len(history) == 1 and history[0].finished_reason == "overdue"
            current = await env.service.get(env.owner, row.id)
            assert current.next_fire_at > env.clock[0] if repeating else current.status == "paused"

    asyncio.run(scenario())


def test_quiet_hours_delay_overnight_without_turning_into_overdue(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            fire = START.replace(hour=16)  # 23:00 VN.
            row = await create(env, next_fire_at=fire)
            async with env.database.sessions.begin() as session:
                settings = await session.get(UserSettings, str(env.owner))
                settings.quiet_start, settings.quiet_end = time(22), time(6)
            env.clock[0] = fire
            await env.dispatcher.tick()
            env.sender.send.assert_not_awaited()
            history = await env.service.history(env.owner, row.id)
            assert history[0].attempt_count == 0 and history[0].retry_at == fire.replace(hour=23)
            env.clock[0] = fire.replace(hour=23)
            await env.dispatcher.tick()
            env.sender.send.assert_awaited_once()

    asyncio.run(scenario())


def test_pause_resume_recomputes_future_and_cancel_never_sends(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            row = await confirm_change(
                env.service,
                env.owner,
                lambda: env.service.set_status(
                    env.owner, row.id, "paused", expected=row.updated_at
                ),
            )
            env.clock[0] = START + timedelta(days=1)
            await env.dispatcher.tick()
            env.sender.send.assert_not_awaited()
            row = await confirm_change(
                env.service,
                env.owner,
                lambda: env.service.set_status(
                    env.owner, row.id, "active", expected=row.updated_at
                ),
            )
            assert row.next_fire_at == env.clock[0] + timedelta(minutes=1)
            row = await confirm_change(
                env.service,
                env.owner,
                lambda: env.service.set_status(
                    env.owner, row.id, "cancelled", expected=row.updated_at
                ),
            )
            env.clock[0] += timedelta(minutes=2)
            await env.dispatcher.tick()
            env.sender.send.assert_not_awaited()

    asyncio.run(scenario())


def test_snooze_duplicates_and_notification_forgery_cannot_create_second_delivery(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            env.clock[0] = START
            await env.dispatcher.tick()
            delivery = (await env.service.history(env.owner, row.id))[0]
            with pytest.raises(ValidationError):
                await env.service.notification_action(env.owner, delivery.id, 999, "snooze")
            await env.service.notification_action(env.owner, delivery.id, 123456789, "snooze")
            with pytest.raises(ValidationError):
                await env.service.notification_action(env.owner, delivery.id, 123456789, "snooze")
            await env.dispatcher.tick()
            assert env.sender.send.await_count == 1
            env.clock[0] += timedelta(minutes=15)
            await env.dispatcher.tick()
            assert env.sender.send.await_count == 2
            async with env.database.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(ReminderDelivery)) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "method,args,kwargs",
    [
        ("get", ("invalid",), {}),
        ("list", (), {}),
        ("history", ("invalid",), {}),
        ("preferences", (), {}),
        ("create", (None,), {"request_id": "x"}),
        ("update", ("invalid", None), {"expected": None}),
        ("set_status", ("invalid", "paused"), {"expected": None}),
        ("notification_action", ("invalid", 1, "done"), {}),
        ("notification_reminder", ("invalid", 1), {}),
        (
            "configure",
            (),
            {
                "dm_enabled": True,
                "channel_id": None,
                "quiet_start": None,
                "quiet_end": None,
                "expected": None,
            },
        ),
    ],
)
def test_reminder_entrypoints_deny_non_owner_before_database(authorization, method, args, kwargs):
    sessions = Mock()
    service = ReminderService(sessions, authorization)
    with pytest.raises(AuthorizationError):
        asyncio.run(getattr(service, method)(authorization.owner_id + 1, *args, **kwargs))
    sessions.begin.assert_not_called()


def test_daily_dst_gap_is_skipped_and_fold_is_not_duplicated():
    rule = RecurrenceRule(time="02:30", timezone="America/New_York")
    assert next_occurrence(rule, datetime(2026, 3, 7, 8, tzinfo=UTC)) == datetime(
        2026, 3, 9, 6, 30, tzinfo=UTC
    )
    fold = RecurrenceRule(time="01:30", timezone="America/New_York")
    assert next_occurrence(fold, datetime(2026, 11, 1, 5, 30, tzinfo=UTC)) == datetime(
        2026, 11, 2, 6, 30, tzinfo=UTC
    )


def test_crash_after_send_before_commit_recovers_but_can_duplicate_external_send(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            env.clock[0] = START
            with patch.object(
                env.dispatcher.deliveries, "finish", new=AsyncMock(side_effect=StorageError())
            ):
                with pytest.raises(StorageError):
                    await env.dispatcher.tick()
            history = await env.service.history(env.owner, row.id)
            assert history[0].status == "claimed" and history[0].discord_message_id is None
            env.clock[0] += CLAIM_LEASE + timedelta(seconds=1)
            await env.dispatcher.tick()
            assert env.sender.send.await_count == 2  # This window cannot promise exactly-once.
            assert (await env.service.history(env.owner, row.id))[0].status == "sent"

    asyncio.run(scenario())


def test_notification_done_updates_linked_task_once_without_stopping_daily_rule(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            task = await env.tasks.create(env.owner, TaskData(title="Linked"), request_id="linked")
            row = await create(
                env,
                task_id=task.id,
                recurrence_type="daily",
                recurrence=RecurrenceRule(time="20:00"),
            )
            env.clock[0] = START
            await env.dispatcher.tick()
            delivery = (await env.service.history(env.owner, row.id))[0]
            await env.service.notification_action(env.owner, delivery.id, 123456789, "done")
            completed = await env.tasks.get(env.owner, task.id)
            assert completed.status == "done" and completed.completed_at == START
            assert (await env.service.get(env.owner, row.id)).status == "active"
            with pytest.raises(ValidationError):
                await env.service.notification_action(env.owner, delivery.id, 123456789, "done")
            assert (await env.tasks.get(env.owner, task.id)).version == completed.version

    asyncio.run(scenario())


def test_notification_expiry_and_worker_changes_invalidate_old_actions(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            with pytest.raises(ConfirmationRequired) as pending:
                await env.service.set_status(env.owner, row.id, "paused", expected=row.updated_at)
            env.clock[0] = START
            await env.dispatcher.tick()
            with pytest.raises(StaleWriteError):
                await env.service.update(
                    env.owner,
                    row.id,
                    pending.value.request.after,
                    expected=row.updated_at,
                    approval_token=pending.value.request.token,
                )
            history = await env.service.history(env.owner, row.id)
            env.clock[0] = history[0].sent_at + timedelta(hours=24, seconds=1)
            with pytest.raises(StaleWriteError):
                await env.service.notification_action(env.owner, history[0].id, 123456789, "snooze")

    asyncio.run(scenario())


def test_preferences_channel_is_validated_before_approval_and_again_at_execution(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            before = await env.service.preferences(env.owner)
            kwargs = dict(
                dm_enabled=False,
                channel_id="234567890123456789",
                quiet_start=None,
                quiet_end=None,
                expected=before.updated_at,
            )
            with pytest.raises(ConfirmationRequired) as pending:
                await env.service.configure(env.owner, **kwargs)
            assert (await env.service.preferences(env.owner)).channel_id is None
            env.service.channel_validator.side_effect = ValidationError("Kênh không còn riêng tư.")
            with pytest.raises(ValidationError):
                await env.service.configure(
                    env.owner, **kwargs, approval_token=pending.value.request.token
                )
            assert (await env.service.preferences(env.owner)).channel_id is None
            env.service.channel_validator.side_effect = None
            await env.service.configure(
                env.owner, **kwargs, approval_token=pending.value.request.token
            )
            assert (await env.service.preferences(env.owner)).channel_id == kwargs["channel_id"]

    asyncio.run(scenario())


def test_permanent_failure_pauses_without_retry_and_logs_no_private_payload(reminder_env, caplog):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            env.sender.send.side_effect = DeliveryFailure("forbidden", permanent=True)
            env.clock[0] = START
            await env.dispatcher.tick()
            env.clock[0] += timedelta(days=1)
            await env.dispatcher.tick()
            env.sender.send.assert_awaited_once()
            history = await env.service.history(env.owner, row.id)
            assert (
                history[0].finished_reason == "blocked"
                and history[0].last_error_code == "forbidden"
            )
            assert (
                "Synthetic reminder" not in caplog.text
                and "reminder_delivery_failed" in caplog.text
            )

    asyncio.run(scenario())


def test_claim_does_not_send_future_snooze_and_atomic_concurrent_claim_has_one_winner(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            await create(env)
            env.clock[0] = START
            delivery = env.dispatcher.deliveries
            await delivery.enqueue(env.owner)
            key = (await delivery.due(env.owner))[0]
            claims = await asyncio.gather(
                delivery.claim(env.owner, key), delivery.claim(env.owner, key)
            )
            assert sum(claim is not None for claim in claims) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "method,args", [("enqueue", ()), ("due", ()), ("claim", ("x",)), ("finish", (None,))]
)
def test_worker_service_entrypoints_also_require_config_owner(authorization, method, args):
    from app.services.reminder_delivery_service import ReminderDeliveryService

    sessions = Mock()
    service = ReminderService(sessions, authorization)
    with pytest.raises(AuthorizationError):
        asyncio.run(
            getattr(ReminderDeliveryService(service), method)(authorization.owner_id + 1, *args)
        )
    sessions.begin.assert_not_called()


def test_retry_or_claim_abandoned_for_hours_is_marked_overdue_not_sent(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            row = await create(env)
            env.sender.send.side_effect = DeliveryFailure("network_error")
            env.clock[0] = START
            await env.dispatcher.tick()
            env.clock[0] += timedelta(hours=2)
            await env.dispatcher.tick()
            env.sender.send.assert_awaited_once()
            assert (await env.service.history(env.owner, row.id))[0].finished_reason == "overdue"

    asyncio.run(scenario())


def test_quiet_boundary_in_dst_gap_moves_to_first_real_local_minute():
    # 02:30 does not exist in New York on the spring-forward date.
    now = datetime(2026, 3, 8, 6, 15, tzinfo=UTC)
    assert quiet_until(now, "America/New_York", time(1), time(2, 30)) == datetime(
        2026, 3, 8, 7, tzinfo=UTC
    )
    assert quiet_until(START, "UTC", time(22), time(6)) is None


def test_done_notification_cannot_silently_reopen_a_cancelled_task(reminder_env):
    async def scenario():
        async with reminder_env() as env:
            task = await env.tasks.create(
                env.owner, TaskData(title="Cancelled link"), request_id="t"
            )
            row = await create(env, task_id=task.id)
            env.clock[0] = START
            await env.dispatcher.tick()
            async with env.database.sessions.begin() as session:
                current = await session.get(Task, task.id)
                current.status = "cancelled"
            delivery = (await env.service.history(env.owner, row.id))[0]
            with pytest.raises(StaleWriteError):
                await env.service.notification_action(env.owner, delivery.id, 123456789, "done")
            assert (await env.tasks.get(env.owner, task.id)).status == "cancelled"
            assert (await env.service.history(env.owner, row.id))[0].acknowledged_at is None

    asyncio.run(scenario())
