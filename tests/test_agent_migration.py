import asyncio

import pytest
from alembic.operations import Operations
from sqlalchemy import inspect, text
from test_reminder_dispatch_migration import migrate, seed_4a

from app.db.backup import backup_database
from app.db.models import Project, Task, UserSettings
from app.db.session import Database

LEGACY = (
    "users",
    "user_settings",
    "projects",
    "tasks",
    "calendar_events",
    "reminders",
    "reminder_deliveries",
    "audit_logs",
)


async def snapshot(database):
    async with database.engine.connect() as connection:
        return {
            name: (await connection.execute(text(f"SELECT * FROM {name}"))).all() for name in LEGACY
        }


async def seed(database):
    await seed_4a(database)
    async with database.engine.begin() as connection:
        await connection.run_sync(lambda conn: migrate(conn, "upgrade", "0004_reminder_dispatch"))
    async with database.sessions.begin() as session:
        session.add(UserSettings(owner_id="123", dm_notifications_enabled=True))
        project = Project(owner_id="123", name="Synthetic migration project")
        session.add(project)
        await session.flush()
        session.add(Task(owner_id="123", project_id=project.id, title="Synthetic migration task"))


def test_p5_upgrade_and_restore_preserve_all_p1_p4_data(settings, tmp_path):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed(database)
            before = await snapshot(database)
        finally:
            await database.close()
        backup = backup_database(tmp_path / "nova.db", tmp_path / "before.db")
        copy = backup_database(backup, tmp_path / "upgrade.db")
        upgraded = Database(f"sqlite+aiosqlite:///{copy}")
        try:
            await upgraded.initialize()
            await upgraded.initialize()
            assert await snapshot(upgraded) == before
            async with upgraded.engine.connect() as connection:
                assert await connection.scalar(text("PRAGMA integrity_check")) == "ok"
                assert not (await connection.execute(text("PRAGMA foreign_key_check"))).all()
            async with upgraded.engine.begin() as connection:
                await connection.run_sync(
                    lambda conn: migrate(conn, "downgrade", "0004_reminder_dispatch")
                )
            assert await snapshot(upgraded) == before
        finally:
            await upgraded.close()
        restored = backup_database(backup, tmp_path / "restore.db")
        recovered = Database(f"sqlite+aiosqlite:///{restored}")
        try:
            assert await snapshot(recovered) == before
        finally:
            await recovered.close()

    asyncio.run(scenario())


def test_partial_migration_failure_restores_revision_and_no_new_tables(settings, monkeypatch):
    create_table = Operations.create_table

    def interrupted(operations, name, *args, **kwargs):
        result = create_table(operations, name, *args, **kwargs)
        if name == "agent_usage":
            raise RuntimeError("synthetic interruption")
        return result

    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed(database)
            before = await snapshot(database)
            with monkeypatch.context() as patcher:
                patcher.setattr(Operations, "create_table", interrupted)
                with pytest.raises(RuntimeError, match="interruption"):
                    await database.initialize()
            assert await snapshot(database) == before
            async with database.engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0004_reminder_dispatch"
                )
                names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert "pending_actions" not in names and "agent_usage" not in names
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("table", ["pending_actions", "agent_usage"])
def test_downgrade_refuses_ai_history(settings, table):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed(database)
            await database.initialize()
            async with database.engine.begin() as connection:
                if table == "pending_actions":
                    await connection.execute(
                        text(
                            "INSERT INTO pending_actions "
                            "(id,owner_id,idempotency_key,action_type,payload_json,status,"
                            "expires_at,created_at,updated_at) VALUES "
                            "('synthetic','123','1','create_task','{}','pending',"
                            "'2030-01-01','2026-01-01','2026-01-01')"
                        )
                    )
                else:
                    await connection.execute(
                        text(
                            "INSERT INTO agent_usage "
                            "(id,owner_id,model,charged_tokens,input_tokens,output_tokens,"
                            "settled,created_at) VALUES "
                            "('synthetic','123','test-model',10,0,0,0,'2026-01-01')"
                        )
                    )
            with pytest.raises(RuntimeError, match="Refusing to discard"):
                async with database.engine.begin() as connection:
                    await connection.run_sync(
                        lambda conn: migrate(conn, "downgrade", "0004_reminder_dispatch")
                    )
            async with database.engine.connect() as connection:
                assert await connection.scalar(text(f"SELECT count(*) FROM {table}")) == 1
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0007_connections"
                )
        finally:
            await database.close()

    asyncio.run(scenario())
