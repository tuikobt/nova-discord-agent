import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.db.models import CalendarEvent, Project, Task, User
from app.db.session import Database

OWNER = "123456789012345678"
OTHER = "223456789012345678"
START = datetime(2026, 10, 25, 20, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
END = START + timedelta(hours=1)


@asynccontextmanager
async def core_database(settings):
    database = Database(settings.database_url)
    try:
        await database.initialize()
        async with database.sessions.begin() as session:
            session.add_all([User(discord_user_id=key, timezone="UTC") for key in (OWNER, OTHER)])
        yield database
    finally:
        await database.close()


def event_values(**changes):
    return {"owner_id": OWNER, "title": "Test event", "starts_at": START, "ends_at": END, **changes}


def test_relationships_defaults_optional_links_and_persistence(settings):
    async def scenario():
        async with core_database(settings) as database:
            async with database.sessions.begin() as session:
                project = Project(owner_id=OWNER, name="Test project", deadline_at=END)
                task = Task(owner_id=OWNER, title="Test task", project=project, due_at=START)
                event = CalendarEvent(**event_values(), task=task)
                standalone = Task(owner_id=OWNER, title="Standalone")
                session.add_all([project, task, event, standalone, CalendarEvent(**event_values())])
                await session.flush()
                ids = project.id, task.id, event.id, standalone.id
                assert len(set(ids)) == 4
                assert all(len(key) == 36 for key in ids)
                assert task.version == event.version == 1
                assert project.status == "active"
                assert task.status == "todo" and task.priority == "medium"
                assert event.status == "proposed" and event.origin == "manual"
                assert event.is_fixed is False
                created = task.created_at
                assert task.updated_at.tzinfo == UTC
        restarted = Database(settings.database_url)
        try:
            await restarted.initialize()
            async with restarted.sessions() as session:
                project = await session.scalar(
                    select(Project)
                    .where(Project.owner_id == OWNER, Project.id == ids[0])
                    .options(selectinload(Project.tasks).selectinload(Task.calendar_events))
                )
                assert [task.id for task in project.tasks] == [ids[1]]
                task = project.tasks[0]
                assert task.calendar_events[0].id == ids[2]
                assert task.created_at == created
                assert task.due_at == START.astimezone(UTC)
                event = task.calendar_events[0]
                assert event.starts_at.tzinfo == UTC
                assert event.starts_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")) == START
                assert event.ends_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")) == END
                standalone = await session.get(Task, ids[3], options=[selectinload(Task.project)])
                assert standalone.project is None
                # Inspect only synthetic test values: SQLite stores normalized UTC without offsets.
                raw = await session.scalar(
                    text("SELECT starts_at FROM calendar_events WHERE id=:id"), {"id": ids[2]}
                )
                assert raw.startswith("2026-10-25 13:00:00")
                linked = await session.get(
                    CalendarEvent,
                    ids[2],
                    options=[selectinload(CalendarEvent.task)],
                    populate_existing=True,
                )
                assert linked.task.id == task.id
        finally:
            await restarted.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "model,values",
    [
        (Project, {"name": ""}),
        (Project, {"name": " \n\t"}),
        (Project, {"name": "x" * 201}),
        (Project, {"name": " " + "x" * 200}),
        (Project, {"status": "invalid"}),
        (Task, {"title": ""}),
        (Task, {"title": "\t"}),
        (Task, {"title": "x" * 251}),
        (Task, {"title": " " + "x" * 250}),
        (Task, {"status": "invalid"}),
        (Task, {"priority": "urgent"}),
        (Task, {"estimated_minutes": 0}),
        (Task, {"estimated_minutes": -1}),
        (Task, {"estimated_minutes": 1.5}),
        (Task, {"estimated_minutes": True}),
        (Task, {"version": 0}),
        (Task, {"version": None}),
        (CalendarEvent, {"title": ""}),
        (CalendarEvent, {"title": "x" * 251}),
        (CalendarEvent, {"title": " " + "x" * 250}),
        (CalendarEvent, {"status": "invalid"}),
        (CalendarEvent, {"origin": "robot"}),
        (CalendarEvent, {"is_fixed": 1}),
        (CalendarEvent, {"version": -1}),
    ],
)
def test_orm_rejects_invalid_values(model, values):
    with pytest.raises((ValueError, TypeError)):
        model(**values)


@pytest.mark.parametrize(
    "model,changes",
    [
        (Project, {"name": " "}),
        (Project, {"name": "x" * 201}),
        (Project, {"name": " " + "x" * 200}),
        (Project, {"name": None}),
        (Project, {"status": "ACTIVE"}),
        (Project, {"owner_id": "missing"}),
        (Project, {"owner_id": None}),
        (Task, {"title": ""}),
        (Task, {"title": "x" * 251}),
        (Task, {"title": " " + "x" * 250}),
        (Task, {"status": "pending"}),
        (Task, {"priority": "urgent"}),
        (Task, {"estimated_minutes": 0}),
        (Task, {"estimated_minutes": -1}),
        (Task, {"estimated_minutes": 1.5}),
        (Task, {"version": 0}),
        (Task, {"version": 1.5}),
        (Task, {"owner_id": "missing"}),
        (Task, {"owner_id": None}),
        (Task, {"project_id": "missing"}),
        (CalendarEvent, {"title": " "}),
        (CalendarEvent, {"title": "x" * 251}),
        (CalendarEvent, {"title": " " + "x" * 250}),
        (CalendarEvent, {"starts_at": None}),
        (CalendarEvent, {"ends_at": START}),
        (CalendarEvent, {"ends_at": START - timedelta(seconds=1)}),
        (CalendarEvent, {"status": "active"}),
        (CalendarEvent, {"origin": "robot"}),
        (CalendarEvent, {"version": -1}),
        (CalendarEvent, {"version": 1.5}),
        (CalendarEvent, {"task_id": "missing"}),
        (CalendarEvent, {"owner_id": "missing"}),
        (CalendarEvent, {"owner_id": None}),
    ],
)
def test_database_constraints_reject_direct_invalid_writes(settings, model, changes):
    async def scenario():
        async with core_database(settings) as database:
            values = (
                {"owner_id": OWNER, "name": "Project"}
                if model is Project
                else ({"owner_id": OWNER, "title": "Task"} if model is Task else event_values())
            )
            with pytest.raises(IntegrityError):
                async with database.sessions.begin() as session:
                    await session.execute(insert(model).values(**{**values, **changes}))
            async with database.sessions() as session:
                assert await session.scalar(select(model.id)) is None

    asyncio.run(scenario())


def test_database_boolean_constraint_cannot_be_bypassed_by_raw_sql(settings):
    async def scenario():
        async with core_database(settings) as database:
            with pytest.raises(IntegrityError):
                async with database.sessions.begin() as session:
                    await session.execute(
                        text(
                            "INSERT INTO calendar_events "
                            "(id, owner_id, title, starts_at, ends_at, is_fixed, "
                            "created_at, updated_at) "
                            "VALUES ('bad', :owner, 'Event', '2026-10-25 13:00:00', "
                            "'2026-10-25 14:00:00', 2, '2026-10-23', '2026-10-23')"
                        ),
                        {"owner": OWNER},
                    )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "operation",
    ["task_insert", "task_update", "event_insert", "event_update", "project_owner", "task_owner"],
)
def test_composite_foreign_keys_reject_cross_owner_links(settings, operation):
    async def scenario():
        async with core_database(settings) as database:
            async with database.sessions.begin() as session:
                project = Project(owner_id=OWNER, name="A")
                task = Task(owner_id=OWNER, title="A", project=project)
                event = CalendarEvent(**event_values(), task=task)
                other_project = Project(owner_id=OTHER, name="B")
                other_task = Task(owner_id=OTHER, title="B", project=other_project)
                session.add_all([project, task, event, other_project, other_task])
                await session.flush()
                project_id, task_id, event_id = project.id, task.id, event.id
                other_project_id, other_task_id = other_project.id, other_task.id
            with pytest.raises(IntegrityError):
                async with database.sessions.begin() as session:
                    if operation == "task_insert":
                        await session.execute(
                            insert(Task).values(owner_id=OTHER, title="Bad", project_id=project_id)
                        )
                    elif operation == "task_update":
                        await session.execute(
                            update(Task)
                            .where(Task.id == task_id)
                            .values(project_id=other_project_id)
                        )
                    elif operation == "event_insert":
                        await session.execute(
                            insert(CalendarEvent).values(
                                **event_values(owner_id=OTHER, task_id=task_id)
                            )
                        )
                    elif operation == "event_update":
                        await session.execute(
                            update(CalendarEvent)
                            .where(CalendarEvent.id == event_id)
                            .values(task_id=other_task_id)
                        )
                    elif operation == "project_owner":
                        await session.execute(
                            update(Project).where(Project.id == project_id).values(owner_id=OTHER)
                        )
                    else:
                        await session.execute(
                            update(Task).where(Task.id == task_id).values(owner_id=OTHER)
                        )
            async with database.sessions() as session:
                assert (await session.get(Task, task_id)).project_id == project_id
                assert (await session.get(CalendarEvent, event_id)).task_id == task_id
                assert await session.scalar(text("PRAGMA foreign_keys")) == 1
                assert (await session.execute(text("PRAGMA foreign_key_check"))).all() == []

    asyncio.run(scenario())


@pytest.mark.parametrize("model", [Task, CalendarEvent])
def test_relationship_assignment_never_changes_owner_to_match_parent(settings, model):
    async def scenario():
        async with core_database(settings) as database:
            async with database.sessions.begin() as session:
                parent = (
                    Project(owner_id=OWNER, name="A")
                    if model is Task
                    else Task(owner_id=OWNER, title="A")
                )
                session.add(parent)
                await session.flush()
                parent_id = parent.id
            with pytest.raises(IntegrityError):
                async with database.sessions.begin() as session:
                    parent = await session.get(Project if model is Task else Task, parent_id)
                    child = (
                        Task(owner_id=OTHER, title="B", project=parent)
                        if model is Task
                        else CalendarEvent(**event_values(owner_id=OTHER), task=parent)
                    )
                    session.add(child)
                    try:
                        await session.flush()
                    finally:
                        assert child.owner_id == OTHER

    asyncio.run(scenario())


@pytest.mark.parametrize("model", [Project, Task, User])
def test_parent_deletion_is_restricted_without_cascading_or_unlinking(settings, model):
    async def scenario():
        async with core_database(settings) as database:
            async with database.sessions.begin() as session:
                project = Project(owner_id=OWNER, name="Project")
                task = Task(owner_id=OWNER, title="Task", project=project)
                event = CalendarEvent(**event_values(), task=task)
                session.add_all([project, task, event])
                await session.flush()
                key = project.id if model is Project else task.id if model is Task else OWNER
                task_id, event_id = task.id, event.id
            with pytest.raises(IntegrityError):
                async with database.sessions.begin() as session:
                    row = await session.get(model, key)
                    await session.delete(row)
            async with database.sessions() as session:
                assert (await session.get(Task, task_id)).project_id == project.id
                assert (await session.get(CalendarEvent, event_id)).task_id == task_id

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "model,field",
    [
        (Project, "deadline_at"),
        (Task, "due_at"),
        (Task, "completed_at"),
        (CalendarEvent, "starts_at"),
        (CalendarEvent, "ends_at"),
    ],
)
def test_core_datetime_fields_reject_naive_values(settings, model, field):
    async def scenario():
        async with core_database(settings) as database:
            values = (
                {"owner_id": OWNER, "name": "P"}
                if model is Project
                else {"owner_id": OWNER, "title": "T"}
                if model is Task
                else event_values()
            )
            values[field] = START.replace(tzinfo=None)
            with pytest.raises(StatementError):
                async with database.sessions.begin() as session:
                    session.add(model(**values))

    asyncio.run(scenario())


def test_failed_unit_of_work_rolls_back_project_task_and_event(settings):
    async def scenario():
        async with core_database(settings) as database:
            with pytest.raises(IntegrityError):
                async with database.sessions.begin() as session:
                    project = Project(owner_id=OWNER, name="P")
                    task = Task(owner_id=OWNER, title="T", project=project)
                    session.add_all([project, task])
                    await session.flush()
                    session.add(CalendarEvent(**event_values(ends_at=START), task=task))
            async with database.sessions() as session:
                for model in (Project, Task, CalendarEvent):
                    assert await session.scalar(select(model.id)) is None

    asyncio.run(scenario())


@pytest.mark.parametrize("local_end_hour,valid", [(21, True), (19, False)])
def test_event_range_uses_utc_instants_when_offsets_differ(settings, local_end_hour, valid):
    async def scenario():
        async with core_database(settings) as database:

            async def save():
                async with database.sessions.begin() as session:
                    session.add(
                        CalendarEvent(
                            **event_values(
                                starts_at=START.astimezone(UTC),
                                ends_at=datetime(
                                    2026,
                                    10,
                                    25,
                                    local_end_hour,
                                    tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
                                ),
                            )
                        )
                    )

            if valid:
                await save()
                async with database.sessions() as session:
                    event = await session.scalar(select(CalendarEvent))
                    assert event.ends_at > event.starts_at
                    assert event.ends_at.tzinfo == UTC
            else:
                with pytest.raises(IntegrityError):
                    await save()

    asyncio.run(scenario())


@pytest.mark.parametrize("model", [Task, CalendarEvent])
def test_orm_versions_reject_stale_writes_and_update_timestamps(settings, model):
    async def scenario():
        async with core_database(settings) as database:
            async with database.sessions.begin() as session:
                row = (
                    Task(owner_id=OWNER, title="T")
                    if model is Task
                    else CalendarEvent(**event_values())
                )
                session.add(row)
                await session.flush()
                key, timestamp = row.id, row.updated_at
            async with database.sessions() as stale:
                old = await stale.get(model, key)
                await stale.commit()  # retain stale snapshot, release SQLite read lock
                async with database.sessions.begin() as fresh:
                    row = await fresh.get(model, key)
                    row.title = "New title"
                old.title = "Stale title"
                with pytest.raises(StaleDataError):
                    await stale.commit()
                await stale.rollback()
            async with database.sessions() as session:
                row = await session.get(model, key)
                assert row.title == "New title" and row.version == 2
                assert row.updated_at >= timestamp and row.updated_at.tzinfo == UTC

    asyncio.run(scenario())


def test_overlapping_confirmed_events_are_not_prohibited_by_database(settings):
    async def scenario():
        async with core_database(settings) as database:
            async with database.sessions.begin() as session:
                session.add_all(
                    [CalendarEvent(**event_values(status="confirmed")) for _ in range(2)]
                )
            async with database.sessions() as session:
                assert len((await session.scalars(select(CalendarEvent))).all()) == 2

    asyncio.run(scenario())
