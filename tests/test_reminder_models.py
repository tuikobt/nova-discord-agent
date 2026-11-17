import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import selectinload

from app.db.models import CalendarEvent, Reminder, ReminderDelivery, Task, User
from app.db.session import Database
from app.domain.errors import ValidationError
from app.domain.reminders import RecurrenceRule, ReminderData

OWNER, OTHER = "123456789012345678", "223456789012345678"
START = datetime(2026, 10, 25, 20, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


@asynccontextmanager
async def store(settings):
    database = Database(settings.database_url)
    try:
        await database.initialize()
        async with database.sessions.begin() as session:
            session.add_all([User(discord_user_id=key, timezone="UTC") for key in (OWNER, OTHER)])
            await session.flush()
            tasks = [Task(owner_id=key, title="Synthetic task") for key in (OWNER, OTHER)]
            session.add_all(tasks)
            await session.flush()
            events = [
                CalendarEvent(
                    owner_id=key,
                    title="Synthetic event",
                    task_id=task.id,
                    starts_at=START,
                    ends_at=START + timedelta(hours=1),
                )
                for key, task in zip((OWNER, OTHER), tasks, strict=True)
            ]
            session.add_all(events)
            await session.flush()
            env = SimpleNamespace(database=database, tasks=tasks, events=events)
        yield env
    finally:
        await database.close()


async def add_reminder(database, **changes):
    async with database.sessions.begin() as session:
        row = Reminder(**{"owner_id": OWNER, "title": "Reminder", "next_fire_at": START, **changes})
        session.add(row)
        await session.flush()
        return row.id


async def add_delivery(database, reminder_id, **changes):
    async with database.sessions.begin() as session:
        row = ReminderDelivery(
            **{"reminder_id": reminder_id, "scheduled_fire_at": START, **changes}
        )
        session.add(row)
        await session.flush()
        return row.id


def test_relationships_defaults_and_utc_survive_restart(settings):
    async def scenario():
        async with store(settings) as env:
            data = ReminderData(
                title="Daily",
                next_fire_at=START,
                recurrence_type="daily",
                recurrence=RecurrenceRule(time="20:00"),
                task_id=env.tasks[0].id,
                event_id=env.events[0].id,
            )
            reminder_id = await add_reminder(env.database, **data.to_storage())
            delivery_id = await add_delivery(env.database, reminder_id)
        restarted = Database(settings.database_url)
        try:
            await restarted.initialize()
            async with restarted.sessions() as session:
                row = await session.get(
                    Reminder,
                    reminder_id,
                    options=[
                        selectinload(Reminder.task),
                        selectinload(Reminder.event),
                        selectinload(Reminder.deliveries),
                    ],
                )
                assert row.owner_id == row.task.owner_id == row.event.owner_id == OWNER
                assert row.created_at.tzinfo == row.updated_at.tzinfo == UTC
                assert row.next_fire_at.tzinfo == UTC
                assert row.next_fire_at == datetime(2026, 10, 25, 13, tzinfo=UTC)
                assert row.status == "active" and row.delivery_target == "dm"
                assert row.recurrence_config_json == {
                    "time": "20:00",
                    "timezone": "Asia/Ho_Chi_Minh",
                }
                delivery = row.deliveries[0]
                assert delivery.id == delivery_id and delivery.status == "pending"
                assert delivery.attempt_count == 0 and delivery.delivery_kind == "scheduled"
                assert delivery.parent_delivery_id is None
                assert delivery.scheduled_fire_at.tzinfo == UTC
                raw = await session.scalar(
                    text("SELECT next_fire_at FROM reminders WHERE id=:id"), {"id": reminder_id}
                )
                assert raw.startswith("2026-10-25 13:00:00")
        finally:
            await restarted.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["task_id", "event_id", "owner_id"])
def test_sql_foreign_keys_reject_missing_and_other_owner_links(settings, field):
    async def scenario():
        async with store(settings) as env:
            values = {
                "owner_id": OWNER,
                "title": "Scoped",
                "next_fire_at": START,
                field: {
                    "task_id": env.tasks[1].id,
                    "event_id": env.events[1].id,
                    "owner_id": "999",
                }[field],
            }
            with pytest.raises(IntegrityError):
                async with env.database.sessions.begin() as session:
                    # Core insert bypasses all mapper and attribute validators.
                    await session.execute(insert(Reminder.__table__).values(**values))
            async with env.database.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(Reminder)) == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["task", "event"])
def test_relationship_assignment_never_rewrites_owner(settings, field):
    async def scenario():
        async with store(settings) as env:
            async with env.database.sessions.begin() as session:
                parent = await session.get(
                    Task if field == "task" else CalendarEvent,
                    env.tasks[1].id if field == "task" else env.events[1].id,
                )
                row = Reminder(owner_id=OWNER, title="Scoped", next_fire_at=START)
                setattr(row, field, parent)
                session.add(row)
                assert row.owner_id == OWNER
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()
                assert row.owner_id == OWNER

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"title": "x" * 251},
        {"status": "sent"},
        {"recurrence_type": "monthly"},
        {"recurrence_type": "daily"},
        {"recurrence_config_json": {"time": "20:00", "timezone": "UTC"}},
        {"delivery_target": "public"},
        {"delivery_target": "channel"},
        {"channel_id": "123"},
        {"task_id": "missing"},
        {"event_id": "missing"},
    ],
)
def test_database_constraints_protect_writes_without_orm_validation(settings, changes):
    async def scenario():
        async with store(settings) as env:
            with pytest.raises(IntegrityError):
                async with env.database.sessions.begin() as session:
                    await session.execute(
                        insert(Reminder.__table__).values(
                            **{"owner_id": OWNER, "title": "Test", "next_fire_at": START, **changes}
                        )
                    )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "changes",
    [
        {
            "recurrence_type": "weekly",
            "recurrence_config_json": {"time": "20:00", "timezone": "UTC"},
        },
        {
            "recurrence_type": "daily",
            "recurrence_config_json": {"time": "20:00", "timezone": "UTC"},
        },
        {
            "recurrence_type": "daily",
            "recurrence_config_json": {"time": "20:00", "timezone": "UTC", "weekday": 6},
        },
        {
            "recurrence_type": "daily",
            "recurrence_config_json": {"time": "25:00", "timezone": "UTC"},
        },
        {
            "recurrence_type": "daily",
            "recurrence_config_json": {"time": "20:00", "timezone": "invalid"},
        },
        {
            "recurrence_type": "daily",
            "recurrence_config_json": {"time": "20:00", "timezone": "UTC", "extra": True},
        },
    ],
)
def test_mapper_revalidates_complete_recurrence_record(settings, changes):
    async def scenario():
        async with store(settings) as env:
            with pytest.raises(ValidationError):
                await add_reminder(env.database, **changes)

    asyncio.run(scenario())


def test_mapper_revalidates_recurrence_on_updates_and_rolls_back(settings):
    async def scenario():
        async with store(settings) as env:
            key = await add_reminder(env.database)
            with pytest.raises(ValidationError):
                async with env.database.sessions.begin() as session:
                    row = await session.get(Reminder, key)
                    row.recurrence_type = "weekly"
                    row.recurrence_config_json = {"time": "20:00", "timezone": "Asia/Ho_Chi_Minh"}
            async with env.database.sessions() as session:
                row = await session.get(Reminder, key)
                assert row.recurrence_type == "none" and row.recurrence_config_json is None

    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["next_fire_at", "scheduled_fire_at", "claimed_at", "sent_at"])
def test_every_reminder_delivery_datetime_rejects_naive_values(settings, field):
    async def scenario():
        async with store(settings) as env:
            with pytest.raises((ValidationError, StatementError)):
                if field == "next_fire_at":
                    await add_reminder(env.database, next_fire_at=START.replace(tzinfo=None))
                else:
                    key = await add_reminder(env.database)
                    await add_delivery(env.database, key, **{field: START.replace(tzinfo=None)})

    asyncio.run(scenario())


def test_same_occurrence_with_different_offsets_has_one_delivery(settings):
    async def scenario():
        async with store(settings) as env:
            key = await add_reminder(env.database)
            await add_delivery(env.database, key)
            with pytest.raises(IntegrityError):
                await add_delivery(env.database, key, scheduled_fire_at=START.astimezone(UTC))
            async with env.database.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(ReminderDelivery)) == 1

    asyncio.run(scenario())


def test_concurrent_occurrence_inserts_cannot_create_duplicate_deliveries(settings):
    async def scenario():
        async with store(settings) as env:
            key = await add_reminder(env.database)
            results = await asyncio.gather(
                add_delivery(env.database, key),
                add_delivery(env.database, key),
                return_exceptions=True,
            )
            assert sum(isinstance(result, IntegrityError) for result in results) == 1
            assert sum(isinstance(result, str) for result in results) == 1
            async with env.database.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(ReminderDelivery)) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "changes",
    [
        {"reminder_id": "missing"},
        {"status": "done"},
        {"attempt_count": -1},
        {"attempt_count": 1.5},
        {"delivery_kind": "other"},
        {"delivery_kind": "snooze"},
        {"parent_delivery_id": "missing"},
        {"last_error_code": "raw response containing private data"},
    ],
)
def test_delivery_constraints_also_protect_direct_sql(settings, changes):
    async def scenario():
        async with store(settings) as env:
            key = await add_reminder(env.database)
            with pytest.raises(IntegrityError):
                async with env.database.sessions.begin() as session:
                    await session.execute(
                        insert(ReminderDelivery.__table__).values(
                            **{"reminder_id": key, "scheduled_fire_at": START, **changes}
                        )
                    )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt_count", True),
        ("attempt_count", 1.5),
        ("attempt_count", -1),
        ("last_error_code", "private-error-payload"),
        ("discord_message_id", "not-an-id"),
    ],
)
def test_delivery_orm_rejects_invalid_counts_ids_and_unclassified_error_text(field, value):
    with pytest.raises(ValueError):
        ReminderDelivery(**{field: value})


def test_snooze_parent_is_same_reminder_unique_and_does_not_replace_recurrence(settings):
    async def scenario():
        async with store(settings) as env:
            key = await add_reminder(
                env.database,
                recurrence_type="daily",
                recurrence_config_json={"time": "20:00", "timezone": "Asia/Ho_Chi_Minh"},
            )
            parent = await add_delivery(env.database, key)
            snooze = await add_delivery(
                env.database,
                key,
                scheduled_fire_at=START + timedelta(minutes=15),
                delivery_kind="snooze",
                parent_delivery_id=parent,
            )
            with pytest.raises(IntegrityError):
                await add_delivery(
                    env.database,
                    key,
                    scheduled_fire_at=START + timedelta(minutes=30),
                    delivery_kind="snooze",
                    parent_delivery_id=parent,
                )
            other_key = await add_reminder(env.database, owner_id=OTHER)
            with pytest.raises(IntegrityError):
                await add_delivery(
                    env.database, other_key, delivery_kind="snooze", parent_delivery_id=parent
                )
            await add_delivery(
                env.database,
                key,
                scheduled_fire_at=START + timedelta(minutes=30),
                delivery_kind="snooze",
                parent_delivery_id=snooze,
            )
            async with env.database.sessions() as session:
                row = await session.get(Reminder, key)
                assert row.next_fire_at == START and row.recurrence_type == "daily"
                assert row.recurrence_config_json["time"] == "20:00"

    asyncio.run(scenario())


@pytest.mark.parametrize("model", [User, Task, CalendarEvent, Reminder, ReminderDelivery])
def test_delete_restrict_never_cascades_personal_data_or_delivery_history(settings, model):
    async def scenario():
        async with store(settings) as env:
            key = await add_reminder(
                env.database, task_id=env.tasks[0].id, event_id=env.events[0].id
            )
            parent = await add_delivery(env.database, key)
            await add_delivery(
                env.database,
                key,
                scheduled_fire_at=START + timedelta(minutes=15),
                delivery_kind="snooze",
                parent_delivery_id=parent,
            )
            primary = model.discord_user_id if model is User else model.id
            target = {
                User: OWNER,
                Task: env.tasks[0].id,
                CalendarEvent: env.events[0].id,
                Reminder: key,
                ReminderDelivery: parent,
            }[model]
            with pytest.raises(IntegrityError):
                async with env.database.sessions.begin() as session:
                    await session.execute(delete(model).where(primary == target))
            async with env.database.sessions() as session:
                assert await session.get(Reminder, key) is not None
                assert await session.scalar(select(func.count()).select_from(ReminderDelivery)) == 2

    asyncio.run(scenario())


def test_delivery_cannot_be_its_own_snooze_parent(settings):
    async def scenario():
        async with store(settings) as env:
            key = await add_reminder(env.database)
            own_id = str(uuid4())
            with pytest.raises(IntegrityError):
                await add_delivery(
                    env.database, key, id=own_id, parent_delivery_id=own_id, delivery_kind="snooze"
                )

    asyncio.run(scenario())


def test_failed_transaction_does_not_keep_partially_inserted_reminder(settings):
    async def scenario():
        async with store(settings) as env:
            with pytest.raises(IntegrityError):
                async with env.database.sessions.begin() as session:
                    reminder = Reminder(owner_id=OWNER, title="Atomic", next_fire_at=START)
                    session.add(reminder)
                    await session.flush()
                    session.add(ReminderDelivery(reminder_id="missing", scheduled_fire_at=START))
            async with env.database.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(Reminder)) == 0

    asyncio.run(scenario())
