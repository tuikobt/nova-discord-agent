import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime, time, timedelta, timezone
from unittest.mock import Mock

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.config import PROJECT_ROOT
from app.db.base import Base
from app.db.models import User, UserSettings
from app.db.repositories.user_repository import UserRepository
from app.db.session import Database
from app.domain.authorization import AuthorizationError, OwnerAuthorization, OwnerMismatchError
from app.services.settings_service import SettingsService


def test_migration_from_empty_database_is_idempotent_and_matches_models(settings):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            await database.initialize()
            async with database.engine.connect() as connection:
                tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert set(tables) == {
                    "users",
                    "user_settings",
                    "audit_logs",
                    "alembic_version",
                    "projects",
                    "tasks",
                    "calendar_events",
                }
                assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
                assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    "0002_core_management"
                )
                differences = await connection.run_sync(
                    lambda conn: compare_metadata(MigrationContext.configure(conn), Base.metadata)
                )
                assert differences == []
        finally:
            await database.close()

    asyncio.run(scenario())


def test_failed_migration_rolls_back_schema_and_can_be_retried(settings, monkeypatch):
    create_table = Operations.create_table

    def fail_after_table_creation(operations, table_name, *args, **kwargs):
        create_table(operations, table_name, *args, **kwargs)
        raise RuntimeError("simulated interrupted migration")

    async def scenario():
        database = Database(settings.database_url)
        try:
            with monkeypatch.context() as patcher:
                patcher.setattr(Operations, "create_table", fail_after_table_creation)
                with pytest.raises(RuntimeError, match="interrupted migration"):
                    await database.initialize()
            async with database.engine.connect() as connection:
                tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert tables == []
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(scenario())


def test_restart_preserves_owner_settings_and_timestamps(settings, authorization):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            service = SettingsService(database.sessions, authorization)
            await service.initialize_owner(settings.owner_id, settings.timezone)
            async with database.sessions.begin() as session:
                user = await session.get(User, str(settings.owner_id))
                created_at = user.created_at
                assert created_at.utcoffset() == timedelta(0)
                preferences = await session.get(UserSettings, str(settings.owner_id))
                assert preferences.morning_briefing_time is None
                preferences.dm_notifications_enabled = False
                preferences.quiet_start = time(22)
                user.timezone = "UTC"
        finally:
            await database.close()

        restarted = Database(settings.database_url)
        try:
            await restarted.initialize()
            service = SettingsService(restarted.sessions, authorization)
            await service.initialize_owner(settings.owner_id, settings.timezone)
            await service.initialize_owner(settings.owner_id, settings.timezone)
            async with restarted.sessions() as session:
                user = await session.get(User, str(settings.owner_id))
                preferences = await session.get(UserSettings, str(settings.owner_id))
                assert user.timezone == "UTC"
                assert user.locale == "vi-VN"
                assert user.created_at == created_at
                assert preferences.dm_notifications_enabled is False
                assert preferences.quiet_start == time(22)
                assert preferences.updated_at.tzinfo == UTC
                assert await session.scalar(select(func.count()).select_from(User)) == 1
                assert await session.scalar(select(func.count()).select_from(UserSettings)) == 1
        finally:
            await restarted.close()

    asyncio.run(scenario())


def test_service_rejects_non_owner_before_opening_session(authorization):
    sessions = Mock()
    service = SettingsService(sessions, authorization)
    with pytest.raises(AuthorizationError):
        asyncio.run(service.initialize_owner(authorization.owner_id + 1, "UTC"))
    sessions.begin.assert_not_called()


def test_changed_config_owner_does_not_take_over_existing_database(settings, authorization):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            await SettingsService(database.sessions, authorization).initialize_owner(
                settings.owner_id, settings.timezone
            )
            new_authorization = OwnerAuthorization(settings.owner_id + 1)
            with pytest.raises(OwnerMismatchError):
                await SettingsService(database.sessions, new_authorization).initialize_owner(
                    new_authorization.owner_id, "UTC"
                )
            async with database.sessions() as session:
                assert await session.get(User, str(new_authorization.owner_id)) is None
                assert await session.get(User, str(settings.owner_id)) is not None
        finally:
            await database.close()

    asyncio.run(scenario())


def test_bootstrap_rolls_back_partial_owner_creation(settings, authorization, monkeypatch):
    async def fail_after_user_insert(repository, owner_id, timezone):
        repository.session.add(User(discord_user_id=owner_id, timezone=timezone))
        await repository.session.flush()
        raise RuntimeError("simulated settings creation failure")

    monkeypatch.setattr(UserRepository, "ensure_owner", fail_after_user_insert)

    async def scenario():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            with pytest.raises(RuntimeError):
                await SettingsService(database.sessions, authorization).initialize_owner(
                    settings.owner_id, settings.timezone
                )
            async with database.sessions() as session:
                assert await session.get(User, str(settings.owner_id)) is None
        finally:
            await database.close()

    asyncio.run(scenario())


def test_foreign_keys_reject_orphan_settings(settings):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            with pytest.raises(IntegrityError):
                async with database.sessions.begin() as session:
                    session.add(UserSettings(owner_id="999"))
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("aware", [True, False])
def test_datetimes_are_normalized_to_utc_and_naive_input_is_rejected(settings, aware):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            value = datetime(
                2026, 10, 23, 7, tzinfo=timezone(timedelta(hours=7)) if aware else None
            )

            async def insert():
                async with database.sessions.begin() as session:
                    session.add(User(discord_user_id="123", timezone="UTC", created_at=value))

            if not aware:
                with pytest.raises(StatementError):
                    await insert()
            else:
                await insert()
                async with database.sessions() as session:
                    user = await session.get(User, "123")
                    assert user.created_at == datetime(2026, 10, 23, tzinfo=UTC)
        finally:
            await database.close()

    asyncio.run(scenario())


def test_alembic_cli_without_discord_credentials(settings):
    test_environment = {**os.environ, "DATABASE_URL": settings.database_url}
    test_environment.pop("DISCORD_TOKEN", None)
    test_environment.pop("DISCORD_OWNER_ID", None)
    for args in (("upgrade", "head"), ("check",), ("downgrade", "base"), ("upgrade", "head")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=PROJECT_ROOT,
            env=test_environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr + result.stdout
