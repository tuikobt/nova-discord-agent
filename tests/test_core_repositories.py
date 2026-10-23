import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError

from app.db.models import CalendarEvent, Project, Task, User
from app.db.repositories.calendar_repository import CalendarRepository
from app.db.repositories.project_repository import ProjectRepository
from app.db.repositories.task_repository import TaskRepository
from app.domain.approvals import ApprovalStore
from app.domain.core import EventData, ProjectData, TaskData
from app.domain.errors import (
    ApprovalInvalidError,
    ConfirmationRequired,
    NotFoundError,
    StorageError,
    ValidationError,
)

START = datetime(2026, 10, 25, 13, tzinfo=UTC)


@pytest.mark.parametrize(
    "repository_type,model",
    [(ProjectRepository, Project), (TaskRepository, Task), (CalendarRepository, CalendarEvent)],
)
def test_repository_queries_updates_and_paging_cannot_access_other_owner(
    core_factory, repository_type, model
):
    async def scenario():
        async with core_factory() as env:
            other = str(env.owner + 1)
            async with env.database.sessions.begin() as session:
                session.add(User(discord_user_id=other, timezone="UTC"))
                await session.flush()
                values = {"name": "Private"} if model is Project else {"title": "Private"}
                if model is CalendarEvent:
                    values.update(starts_at=START, ends_at=START + timedelta(hours=1))
                row = model(owner_id=other, **values)
                session.add(row)
                await session.flush()
                key, stamp = row.id, row.updated_at if model is Project else row.version
            async with env.database.sessions.begin() as session:
                repository = repository_type(session, str(env.owner))
                with pytest.raises(NotFoundError):
                    await repository.get(key)
                assert await repository.get(key, required=False) is None
                # Even a query missing the scope cannot bypass paging's owner predicate.
                rows, total = await repository.page(select(model), 0, 10)
                assert rows == () and total == 0
                from app.domain.errors import StaleWriteError

                with pytest.raises(StaleWriteError):
                    await repository.update(key, values, stamp)
            async with env.database.sessions() as session:
                assert (await session.get(model, key)).owner_id == other

    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["id", "owner_id", "version", "origin"])
def test_repository_rejects_fields_that_could_change_identity_or_bypass_versioning(
    core_factory, field
):
    async def scenario():
        async with core_factory() as env:
            async with env.database.sessions.begin() as session:
                for repository_type in (ProjectRepository, TaskRepository, CalendarRepository):
                    repository = repository_type(session, str(env.owner))
                    with pytest.raises(ValidationError):
                        await repository.add(str(uuid4()), {field: "forged"})
                    with pytest.raises(ValidationError):
                        await repository.update(str(uuid4()), {field: "forged"}, 1)

    asyncio.run(scenario())


def test_services_persist_after_database_restart_without_losing_settings(core_factory):
    async def scenario():
        async with core_factory() as env:
            project = await env.projects.create(
                env.owner, ProjectData(name="Persistent"), request_id="p"
            )
            task = await env.tasks.create(
                env.owner, TaskData(title="Persistent", project_id=project.id), request_id="t"
            )
            event_data = EventData(
                title="Persistent",
                starts_at=START,
                ends_at=START + timedelta(hours=1),
                task_id=task.id,
            )
            calendar = await env.calendar.create(env.owner, event_data, request_id="e")
        async with core_factory() as restarted:
            assert await restarted.projects.get(restarted.owner, project.id) == project
            assert await restarted.tasks.get(restarted.owner, task.id) == task
            assert await restarted.calendar.get(restarted.owner, calendar.id) == calendar
            assert (
                await restarted.calendar.create(restarted.owner, event_data, request_id="e")
            ).id == calendar.id

    asyncio.run(scenario())


def test_failed_approved_commit_retains_pending_action_for_safe_retry(core_factory):
    async def scenario():
        async with core_factory() as env:
            task = await env.tasks.create(env.owner, TaskData(title="T"), request_id="t")
            with pytest.raises(ConfirmationRequired) as pending:
                await env.tasks.set_status(env.owner, task.id, "cancelled", expected=1)
            token = pending.value.request.token

            def fail_commit(connection):
                raise OperationalError("private SQL", {}, Exception("hidden"))

            event.listen(env.database.engine.sync_engine, "commit", fail_commit)
            try:
                with pytest.raises(StorageError):
                    await env.tasks.set_status(
                        env.owner, task.id, "cancelled", expected=1, approval_token=token
                    )
            finally:
                event.remove(env.database.engine.sync_engine, "commit", fail_commit)
            assert (await env.tasks.get(env.owner, task.id)).status == "todo"
            result = await env.tasks.set_status(
                env.owner, task.id, "cancelled", expected=1, approval_token=token
            )
            assert result.status == "cancelled"
            # A used cancellation token cannot authorize a different update even with fresh version.
            with pytest.raises(ApprovalInvalidError):
                await env.tasks.update(
                    env.owner,
                    task.id,
                    TaskData(title="Forged"),
                    expected=result.version,
                    approval_token=token,
                )

    asyncio.run(scenario())


def test_manual_approval_store_is_owner_bound_and_bounded():
    store = ApprovalStore(clock=lambda: START)
    request = store.issue("owner", "fingerprint", reason="test", before=None, after=None)
    with pytest.raises(ApprovalInvalidError):
        store.check(request.token, "other-owner", "fingerprint")
    with pytest.raises(ApprovalInvalidError):
        store.check(request.token, "owner", "other-payload")
    store.check(request.token, "owner", "fingerprint")
    store.consume(request.token)
    with pytest.raises(ApprovalInvalidError):
        store.check(request.token, "owner", "fingerprint")
    for _ in range(100):
        store.issue("owner", "fingerprint", reason="test", before=None, after=None)
    with pytest.raises(ValidationError):
        store.issue("owner", "fingerprint", reason="test", before=None, after=None)
