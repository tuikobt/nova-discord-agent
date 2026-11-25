import asyncio
import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime, time, timedelta

import pytest
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from sqlalchemy import inspect, text

from app.config import PROJECT_ROOT
from app.db.backup import backup_database
from app.db.models import (
    AuditLog,
    CalendarEvent,
    Project,
    Reminder,
    ReminderDelivery,
    Task,
    User,
    UserSettings,
)
from app.db.session import Database

LEGACY = ("users", "user_settings", "audit_logs", "projects", "tasks", "calendar_events")
OWNER = "123456789012345678"
START = datetime(2026, 10, 25, 13, tzinfo=UTC)


def migrate(connection, action, revision):
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.attributes["connection"] = connection
    getattr(command, action)(config, revision)


async def seed_phase3(database):
    async with database.engine.begin() as connection:
        await connection.run_sync(lambda conn: migrate(conn, "upgrade", "0002_core_management"))
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
            AuditLog(owner_id=OWNER, actor="system", action="synthetic.seed", result="success")
        )
        project = Project(owner_id=OWNER, name="Synthetic P3 project", deadline_at=START)
        session.add(project)
        await session.flush()
        task = Task(owner_id=OWNER, project_id=project.id, title="Synthetic P3 task", due_at=START)
        session.add(task)
        await session.flush()
        session.add(
            CalendarEvent(
                owner_id=OWNER,
                task_id=task.id,
                title="Synthetic P3 event",
                starts_at=START,
                ends_at=START + timedelta(hours=1),
                status="confirmed",
                is_fixed=True,
            )
        )


async def snapshot(database):
    async with database.engine.connect() as connection:
        # Trusted table names and synthetic records only; never print row contents.
        rows = {
            table: (await connection.execute(text(f"SELECT * FROM {table} ORDER BY 1"))).all()
            for table in LEGACY
        }
        definitions = (
            await connection.execute(
                text("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
            )
        ).all()
        return rows, {name: sql for name, sql in definitions if name in LEGACY}


async def revision(database):
    async with database.engine.connect() as connection:
        return await connection.scalar(text("SELECT version_num FROM alembic_version"))


def test_backup_upgrade_empty_downgrade_reupgrade_and_restore_preserve_every_p1_p3_column(
    settings, tmp_path
):
    async def scenario():
        source = Database(settings.database_url)
        try:
            await seed_phase3(source)
            before = await snapshot(source)
        finally:
            await source.close()
        path = tmp_path / "nova.db"
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        backup = backup_database(path, tmp_path / "pre-phase-4a.db")
        working = backup_database(backup, tmp_path / "phase-4a-copy.db")
        database = Database(f"sqlite+aiosqlite:///{working}")
        try:
            await database.initialize()
            await database.initialize()
            assert await revision(database) == "0007_connections"
            assert await snapshot(database) == before
            async with database.engine.connect() as connection:
                assert (await connection.execute(text("PRAGMA foreign_key_check"))).all() == []
                assert await connection.scalar(text("PRAGMA integrity_check")) == "ok"
                indexes = await connection.run_sync(
                    lambda conn: inspect(conn).get_indexes("calendar_events")
                )
                composite = next(
                    item for item in indexes if item["name"] == "ux_calendar_events_id_owner"
                )
                assert composite["unique"] and composite["column_names"] == ["id", "owner_id"]
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda conn: migrate(conn, "downgrade", "0002_core_management")
                )
            assert await snapshot(database) == before
            assert await revision(database) == "0002_core_management"
            await database.initialize()
            assert await snapshot(database) == before
        finally:
            await database.close()
        restored = backup_database(backup, tmp_path / "restored-phase3.db")
        recovered = Database(f"sqlite+aiosqlite:///{restored}")
        try:
            assert await snapshot(recovered) == before
            assert await revision(recovered) == "0002_core_management"
        finally:
            await recovered.close()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before_hash

    asyncio.run(scenario())


def test_interrupted_p4_upgrade_rolls_back_new_tables_index_and_version(settings, monkeypatch):
    create_table = Operations.create_table

    def interrupted(operations, table_name, *args, **kwargs):
        result = create_table(operations, table_name, *args, **kwargs)
        if table_name == "reminder_deliveries":
            raise RuntimeError("synthetic interrupted P4 DDL")
        return result

    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed_phase3(database)
            before = await snapshot(database)
            with monkeypatch.context() as patcher:
                patcher.setattr(Operations, "create_table", interrupted)
                with pytest.raises(RuntimeError, match="interrupted P4"):
                    await database.initialize()
            assert await snapshot(database) == before
            assert await revision(database) == "0002_core_management"
            async with database.engine.connect() as connection:
                tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert set(tables) == {*LEGACY, "alembic_version"}
                indexes = await connection.run_sync(
                    lambda conn: inspect(conn).get_indexes("calendar_events")
                )
                assert "ux_calendar_events_id_owner" not in {item["name"] for item in indexes}
            await database.initialize()
            assert await snapshot(database) == before
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("with_delivery", [False, True])
def test_downgrade_refuses_to_discard_even_terminal_reminder_records(settings, with_delivery):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed_phase3(database)
            await database.initialize()
            before = await snapshot(database)
            async with database.sessions.begin() as session:
                row = Reminder(
                    owner_id=OWNER, title="Retain history", next_fire_at=START, status="done"
                )
                session.add(row)
                await session.flush()
                key = row.id
                if with_delivery:
                    session.add(ReminderDelivery(reminder_id=key, scheduled_fire_at=START))
            with pytest.raises(RuntimeError, match="bảng P4 có dữ liệu|lịch sử delivery"):
                async with database.engine.begin() as connection:
                    await connection.run_sync(
                        lambda conn: migrate(conn, "downgrade", "0002_core_management")
                    )
            assert await revision(database) == "0007_connections"
            assert await snapshot(database) == before
            async with database.sessions() as session:
                assert (await session.get(Reminder, key)).status == "done"
        finally:
            await database.close()

    asyncio.run(scenario())


def test_offline_downgrade_is_rejected_without_creating_a_database(tmp_path):
    path = tmp_path / "not-created.db"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0003_reminders:0002_core_management",
            "--sql",
        ],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite+aiosqlite:///{path}",
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode != 0 and "Downgrade cần kết nối DB" in result.stderr
    assert not path.exists()
