import asyncio
from datetime import UTC, datetime, time

import pytest
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from sqlalchemy import inspect, select, text

from app.config import PROJECT_ROOT
from app.db.backup import backup_database
from app.db.models import AuditLog, CalendarEvent, Project, Task, User, UserSettings
from app.db.session import Database

FOUNDATION = {"users", "user_settings", "audit_logs", "alembic_version"}
CORE = {"projects", "tasks", "calendar_events"}
OWNER = "123456789012345678"


def migrate(connection, action, revision):
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.attributes["connection"] = connection
    getattr(command, action)(config, revision)


async def seed_phase2(database):
    async with database.engine.begin() as connection:
        await connection.run_sync(lambda conn: migrate(conn, "upgrade", "0001_foundation"))
    async with database.sessions.begin() as session:
        session.add(User(discord_user_id=OWNER, timezone="Asia/Ho_Chi_Minh", locale="vi-VN"))
        await session.flush()
        session.add(
            UserSettings(
                owner_id=OWNER,
                dashboard_channel_id="234567890123456789",
                dashboard_message_id="345678901234567890",
                quiet_start=time(22),
                quiet_end=time(6),
                dm_notifications_enabled=False,
            )
        )
        session.add(
            AuditLog(owner_id=OWNER, actor="system", action="test.bootstrap", result="success")
        )


async def foundation_snapshot(database):
    async with database.engine.connect() as connection:
        # Only fixed, trusted table names; never emit user values in test output.
        return {
            table: (await connection.execute(text(f"SELECT * FROM {table}"))).all()
            for table in ("users", "user_settings", "audit_logs")
        }


def test_upgrade_from_phase2_backup_preserves_every_foundation_column_and_indexes(
    settings, tmp_path
):
    async def scenario():
        original = Database(settings.database_url)
        try:
            await seed_phase2(original)
            before = await foundation_snapshot(original)
        finally:
            await original.close()
        backup = backup_database(tmp_path / "nova.db", tmp_path / "phase2-backup.db")
        working = backup_database(backup, tmp_path / "phase3-copy.db")
        upgraded = Database(f"sqlite+aiosqlite:///{working}")
        try:
            await upgraded.initialize()
            await upgraded.initialize()
            assert await foundation_snapshot(upgraded) == before
            async with upgraded.engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0002_core_management"
                )
                assert (await connection.execute(text("PRAGMA foreign_key_check"))).all() == []
                for table, indexes in {
                    "projects": {"ix_projects_owner_status"},
                    "tasks": {"ix_tasks_owner_status_due", "ix_tasks_project_status"},
                    "calendar_events": {
                        "ix_calendar_events_owner_range",
                        "ix_calendar_events_task_owner",
                    },
                }.items():
                    actual = await connection.run_sync(
                        lambda conn, table=table: inspect(conn).get_indexes(table)
                    )
                    assert {item["name"] for item in actual} == indexes
            # Restore drill into another new file: backup remains at the old revision.
            restored = backup_database(backup, tmp_path / "restored.db")
            recovered = Database(f"sqlite+aiosqlite:///{restored}")
            try:
                assert await foundation_snapshot(recovered) == before
                async with recovered.engine.connect() as connection:
                    assert (
                        await connection.scalar(text("SELECT version_num FROM alembic_version"))
                        == "0001_foundation"
                    )
            finally:
                await recovered.close()
        finally:
            await upgraded.close()

    asyncio.run(scenario())


def test_interrupted_upgrade_rolls_back_only_new_schema_and_preserves_phase2(settings, monkeypatch):
    create_table = Operations.create_table

    def interrupted(operations, table_name, *args, **kwargs):
        result = create_table(operations, table_name, *args, **kwargs)
        if table_name == "tasks":
            raise RuntimeError("test interruption after tasks DDL")
        return result

    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed_phase2(database)
            before = await foundation_snapshot(database)
            with monkeypatch.context() as patcher:
                patcher.setattr(Operations, "create_table", interrupted)
                with pytest.raises(RuntimeError, match="test interruption"):
                    await database.initialize()
            assert await foundation_snapshot(database) == before
            async with database.engine.connect() as connection:
                tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert set(tables) == FOUNDATION
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0001_foundation"
                )
            await database.initialize()
            assert await foundation_snapshot(database) == before
        finally:
            await database.close()

    asyncio.run(scenario())


def test_empty_core_downgrade_and_reupgrade_preserve_phase2(settings):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed_phase2(database)
            before = await foundation_snapshot(database)
            await database.initialize()
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda conn: migrate(conn, "downgrade", "0001_foundation")
                )
            assert await foundation_snapshot(database) == before
            async with database.engine.connect() as connection:
                tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert set(tables) == FOUNDATION
            await database.initialize()
            assert await foundation_snapshot(database) == before
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("model", [Project, Task, CalendarEvent])
def test_downgrade_refuses_to_discard_core_records(settings, model):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed_phase2(database)
            await database.initialize()
            async with database.sessions.begin() as session:
                values = (
                    {"owner_id": OWNER, "name": "P"}
                    if model is Project
                    else {"owner_id": OWNER, "title": "T"}
                )
                if model is CalendarEvent:
                    values.update(
                        starts_at=datetime(2026, 10, 25, 13, tzinfo=UTC),
                        ends_at=datetime(2026, 10, 25, 14, tzinfo=UTC),
                    )
                session.add(model(**values))
            before = await foundation_snapshot(database)
            with pytest.raises(RuntimeError, match="Không downgrade"):
                async with database.engine.begin() as connection:
                    await connection.run_sync(
                        lambda conn: migrate(conn, "downgrade", "0001_foundation")
                    )
            assert await foundation_snapshot(database) == before
            async with database.sessions() as session:
                assert await session.scalar(select(model.id)) is not None
            async with database.engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0002_core_management"
                )
                tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert set(tables) == FOUNDATION | CORE
        finally:
            await database.close()

    asyncio.run(scenario())
