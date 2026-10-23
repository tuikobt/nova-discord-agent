import asyncio
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.db.models import CalendarEvent, Project, Task, User
from app.db.repositories.task_repository import TaskRepository
from app.domain.core import EventData, ProjectData, TaskData, to_record
from app.domain.errors import (
    ConfirmationRequired,
    DuplicateRequestError,
    NotFoundError,
    StaleWriteError,
    StorageError,
    ValidationError,
)

START = datetime(2026, 10, 25, 13, tzinfo=UTC)


def test_project_task_crud_progress_completed_at_and_linked_event_survives(core_factory):
    async def scenario():
        async with core_factory() as env:
            owner, projects, tasks = env.owner, env.projects, env.tasks
            project = await projects.create(owner, ProjectData(name=" Project "), request_id="p")
            assert project.name == "Project"
            assert (await projects.progress(owner, project.id)).percent == 0
            assert "Chưa có nhiệm vụ" in (await projects.progress(owner, project.id)).description
            task = await tasks.create(
                owner,
                TaskData(title="Task", project_id=project.id, estimated_minutes=30, due_at=START),
                request_id="t",
            )
            second = await tasks.create(
                owner, TaskData(title="Second", project_id=project.id), request_id="t2"
            )
            event = await env.calendar.create(
                owner,
                EventData(
                    title="Block",
                    starts_at=START,
                    ends_at=START + timedelta(hours=1),
                    task_id=task.id,
                ),
                request_id="e",
            )
            done = await tasks.set_status(owner, task.id, "done", expected=task.version)
            assert done.completed_at is not None and done.completed_at.tzinfo == UTC
            progress = await projects.progress(owner, project.id)
            assert (progress.done, progress.total, progress.percent) == (1, 2, 50)
            assert "số lượng" in progress.description
            edited = await tasks.update(
                owner,
                task.id,
                replace(to_record(TaskData, done), priority="high"),
                expected=done.version,
            )
            assert edited.completed_at == done.completed_at
            reopened = await tasks.set_status(owner, task.id, "doing", expected=edited.version)
            assert reopened.completed_at is None and reopened.version == 4
            assert (await env.calendar.get(owner, event.id)).task_id == task.id
            assert (await env.calendar.get(owner, event.id)).status == "confirmed"
            with pytest.raises(ConfirmationRequired) as pending:
                await tasks.set_status(owner, second.id, "cancelled", expected=second.version)
            assert (await tasks.get(owner, second.id)).status == "todo"
            await tasks.set_status(
                owner,
                second.id,
                "cancelled",
                expected=second.version,
                approval_token=pending.value.request.token,
            )
            assert (await projects.progress(owner, project.id)).total == 1
            updated = await projects.update(
                owner,
                project.id,
                ProjectData(
                    name="Updated", description="Details", status="paused", deadline_at=START
                ),
                expected=project.updated_at,
            )
            assert updated.name == "Updated" and updated.status == "paused"
            assert updated.updated_at > project.updated_at
            with pytest.raises(ConfirmationRequired) as pending:
                await projects.archive(owner, project.id, expected=updated.updated_at)
            archived = await projects.archive(
                owner,
                project.id,
                expected=updated.updated_at,
                approval_token=pending.value.request.token,
            )
            assert archived.status == "archived"
            assert (await tasks.get(owner, task.id)).project_id == project.id
            restored = await projects.update(
                owner,
                project.id,
                replace(to_record(ProjectData, archived), status="active"),
                expected=archived.updated_at,
            )
            assert restored.status == "active"
            with pytest.raises(FrozenInstanceError):
                restored.name = "Cannot mutate snapshot"

    asyncio.run(scenario())


def test_task_filters_pagination_clear_values_and_project_membership(core_factory):
    async def scenario():
        async with core_factory() as env:
            owner, tasks = env.owner, env.tasks
            p = await env.projects.create(owner, ProjectData(name="P"), request_id="p")
            records = []
            for index in range(5):
                records.append(
                    await tasks.create(
                        owner,
                        TaskData(
                            title=f"T{index}",
                            project_id=p.id,
                            priority="high" if index < 3 else "low",
                            due_at=START + timedelta(hours=index),
                        ),
                        request_id=str(index),
                    )
                )
            first = await tasks.list(owner, project_id=p.id, priority="high", page_size=2)
            second = await tasks.list(owner, project_id=p.id, priority="high", page=1, page_size=2)
            assert first.total == second.total == 3
            assert len(first.items) == 2 and len(second.items) == 1
            assert {row.id for row in first.items}.isdisjoint(row.id for row in second.items)
            window = await tasks.list(
                owner, due_from=START + timedelta(hours=1), due_until=START + timedelta(hours=3)
            )
            assert {row.id for row in window.items} == {records[1].id, records[2].id}
            empty = await tasks.list(owner, page=10)
            assert empty.items == () and empty.total == 5
            changed = await tasks.update(
                owner,
                records[0].id,
                TaskData(
                    title="Unlinked",
                    description=None,
                    project_id=None,
                    due_at=None,
                    estimated_minutes=None,
                ),
                expected=1,
            )
            assert (
                changed.project_id
                is changed.due_at
                is changed.description
                is changed.estimated_minutes
                is None
            )
            assert (await tasks.list(owner, project_id=p.id)).total == 4
            assert (await tasks.list(owner, status="done")).items == ()
            assert (await env.projects.list(owner, status="active")).total == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["projects", "tasks", "calendar"])
def test_creation_is_idempotent_across_service_recreation_and_rejects_changed_payload(
    core_factory, kind
):
    async def scenario():
        async with core_factory() as env:
            service = getattr(env, kind)
            data = (
                ProjectData(name="P")
                if kind == "projects"
                else TaskData(title="T")
                if kind == "tasks"
                else EventData(title="E", starts_at=START, ends_at=START + timedelta(hours=1))
            )
            original = await service.create(env.owner, data, request_id="same-request")
            recreated = type(service)(env.database.sessions, service.authorization)
            repeated = await recreated.create(env.owner, data, request_id="same-request")
            assert repeated == original
            changed = replace(
                data, **({"name": "Changed"} if kind == "projects" else {"title": "Changed"})
            )
            with pytest.raises(DuplicateRequestError):
                await recreated.create(env.owner, changed, request_id="same-request")

    asyncio.run(scenario())


def test_stale_writes_and_duplicate_status_do_not_overwrite_data(core_factory):
    async def scenario():
        async with core_factory() as env:
            p = await env.projects.create(env.owner, ProjectData(name="P"), request_id="p")
            await env.projects.update(
                env.owner, p.id, ProjectData(name="New"), expected=p.updated_at
            )
            with pytest.raises(StaleWriteError):
                await env.projects.update(
                    env.owner, p.id, ProjectData(name="Stale"), expected=p.updated_at
                )
            t = await env.tasks.create(env.owner, TaskData(title="T"), request_id="t")
            await env.tasks.set_status(env.owner, t.id, "done", expected=1)
            with pytest.raises(StaleWriteError):
                await env.tasks.set_status(env.owner, t.id, "done", expected=1)
            assert (await env.projects.get(env.owner, p.id)).name == "New"
            assert (await env.tasks.get(env.owner, t.id)).version == 2

    asyncio.run(scenario())


def test_concurrent_duplicate_create_and_stale_updates_are_serialized(core_factory):
    async def scenario():
        async with core_factory() as env:
            results = await asyncio.gather(
                *(
                    env.tasks.create(env.owner, TaskData(title="Same"), request_id="duplicate")
                    for _ in range(4)
                )
            )
            assert len({row.id for row in results}) == 1
            assert (await env.tasks.list(env.owner)).total == 1
            results = await asyncio.gather(
                *(
                    env.tasks.set_status(env.owner, results[0].id, "done", expected=1)
                    for _ in range(3)
                ),
                return_exceptions=True,
            )
            assert sum(isinstance(result, StaleWriteError) for result in results) == 2
            assert sum(not isinstance(result, Exception) for result in results) == 1

    asyncio.run(scenario())


def test_failed_create_flush_and_commit_do_not_report_success_or_persist_partial_data(
    core_factory, monkeypatch
):
    add = TaskRepository.add

    async def interrupted(repository, record_id, values):
        await add(repository, record_id, values)
        raise OperationalError("hidden SQL", {}, Exception("private payload"))

    async def scenario():
        async with core_factory() as env:
            with monkeypatch.context() as patch:
                patch.setattr(TaskRepository, "add", interrupted)
                with pytest.raises(StorageError) as error:
                    await env.tasks.create(env.owner, TaskData(title="T"), request_id="retry")
                assert "private" not in str(error.value) and "SQL" not in str(error.value)
            assert (await env.tasks.list(env.owner)).total == 0

            # sessionmaker.begin uses transaction.commit, so inject the actual commit event.
            def commit_failure(connection):
                raise OperationalError("hidden SQL", {}, Exception("private payload"))

            from sqlalchemy import event

            event.listen(env.database.engine.sync_engine, "commit", commit_failure)
            try:
                with pytest.raises(StorageError):
                    await env.tasks.create(env.owner, TaskData(title="T"), request_id="retry")
            finally:
                event.remove(env.database.engine.sync_engine, "commit", commit_failure)
            assert (await env.tasks.list(env.owner)).total == 0
            assert (
                await env.tasks.create(env.owner, TaskData(title="T"), request_id="retry")
            ).version == 1

    asyncio.run(scenario())


def test_unknown_and_foreign_owner_ids_are_indistinguishable_and_links_rejected(core_factory):
    async def scenario():
        async with core_factory() as env:
            other = str(env.owner + 1)
            async with env.database.sessions.begin() as session:
                session.add(User(discord_user_id=other, timezone="UTC"))
                await session.flush()
                p = Project(owner_id=other, name="Private")
                t = Task(owner_id=other, title="Private", project=p)
                e = CalendarEvent(
                    owner_id=other,
                    title="Private",
                    starts_at=START,
                    ends_at=START + timedelta(hours=1),
                    task=t,
                    status="confirmed",
                )
                session.add_all([p, t, e])
                await session.flush()
                p_id, t_id, e_id = p.id, t.id, e.id
            for service, key in ((env.projects, p_id), (env.tasks, t_id), (env.calendar, e_id)):
                with pytest.raises(NotFoundError) as foreign:
                    await service.get(env.owner, key)
                with pytest.raises(NotFoundError) as missing:
                    await service.get(env.owner, str(uuid4()))
                assert str(foreign.value) == str(missing.value)
            with pytest.raises(NotFoundError):
                await env.projects.progress(env.owner, p_id)
            with pytest.raises(NotFoundError):
                await env.tasks.create(
                    env.owner, TaskData(title="T", project_id=p_id), request_id="bad"
                )
            with pytest.raises(NotFoundError):
                await env.tasks.list(env.owner, project_id=p_id)
            with pytest.raises(NotFoundError):
                await env.calendar.create(
                    env.owner,
                    EventData(
                        title="E", starts_at=START, ends_at=START + timedelta(hours=1), task_id=t_id
                    ),
                    request_id="bad",
                )
            own = await env.tasks.create(env.owner, TaskData(title="Own"), request_id="own")
            with pytest.raises(NotFoundError):
                await env.tasks.update(
                    env.owner, own.id, TaskData(title="Own", project_id=p_id), expected=1
                )
            assert (await env.projects.list(env.owner)).total == 0
            assert (await env.tasks.list(env.owner)).total == 1
            assert (await env.calendar.list(env.owner, START, START + timedelta(days=1))).total == 0
            async with env.database.sessions() as session:
                assert (await session.scalar(select(Task).where(Task.id == t_id))).owner_id == other

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "options",
    [{"page": -1}, {"page": True}, {"page_size": 0}, {"page_size": 51}, {"status": "invalid"}],
)
def test_invalid_list_options_are_business_errors(core_factory, options):
    async def scenario():
        async with core_factory() as env:
            for service in (env.projects, env.tasks):
                with pytest.raises(ValidationError):
                    await service.list(env.owner, **options)
            with pytest.raises(ValidationError):
                await env.calendar.list(env.owner, START, START + timedelta(hours=1), **options)

    asyncio.run(scenario())
