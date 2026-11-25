import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic.operations import Operations
from sqlalchemy import inspect, text
from test_agent import NOW
from test_agent_migration import LEGACY, seed
from test_reminder_dispatch_migration import migrate

from app.db.backup import backup_database
from app.db.models import AgentUsage, AutomationPolicy, AutomationRun, MemoryEntry
from app.db.session import Database

OLD = (*LEGACY, "pending_actions", "agent_usage")


async def snapshot(db):
    async with db.engine.connect() as connection:
        return {
            name: (await connection.execute(text(f"SELECT * FROM {name}"))).all() for name in OLD
        }


async def phase5(db):
    await seed(db)
    async with db.engine.begin() as connection:
        await connection.run_sync(lambda conn: migrate(conn, "upgrade", "0005_agent"))
        await connection.execute(
            text(
                "INSERT INTO agent_usage (id,owner_id,model,charged_tokens,input_tokens,"
                "output_tokens,settled,created_at) "
                "VALUES ('legacy','123','test-model',12,10,2,1,'2026-11-18')"
            )
        )


def test_phase6_backup_upgrade_restore_and_empty_downgrade_preserve_all_columns(settings, tmp_path):
    async def scenario():
        db = Database(settings.database_url)
        try:
            await phase5(db)
            before = await snapshot(db)
        finally:
            await db.close()
        backup = backup_database(tmp_path / "nova.db", tmp_path / "before-phase6.db")
        copied = backup_database(backup, tmp_path / "upgrade-copy.db")
        upgraded = Database(f"sqlite+aiosqlite:///{copied}")
        try:
            await upgraded.initialize()
            await upgraded.initialize()
            after = await snapshot(upgraded)
            assert {k: v for k, v in after.items() if k != "agent_usage"} == {
                k: v for k, v in before.items() if k != "agent_usage"
            }
            assert [tuple(row)[:-1] for row in after["agent_usage"]] == [
                tuple(row) for row in before["agent_usage"]
            ]
            assert all(row[-1] == "dm" for row in after["agent_usage"])
            async with upgraded.engine.begin() as connection:
                assert await connection.scalar(text("PRAGMA integrity_check")) == "ok"
                assert not (await connection.execute(text("PRAGMA foreign_key_check"))).all()
                await connection.run_sync(lambda conn: migrate(conn, "downgrade", "0005_agent"))
            assert await snapshot(upgraded) == before
        finally:
            await upgraded.close()
        restored = backup_database(backup, tmp_path / "restored-copy.db")
        recovered = Database(f"sqlite+aiosqlite:///{restored}")
        try:
            assert await snapshot(recovered) == before
        finally:
            await recovered.close()

    asyncio.run(scenario())


def test_failed_phase6_migration_rolls_back_column_tables_and_revision(settings, monkeypatch):
    async def scenario():
        db = Database(settings.database_url)
        try:
            await phase5(db)
            before = await snapshot(db)
            create = Operations.create_table

            def fail(op, name, *args, **kwargs):
                result = create(op, name, *args, **kwargs)
                if name == "automation_runs":
                    raise RuntimeError("synthetic interruption")
                return result

            with monkeypatch.context() as patch:
                patch.setattr(Operations, "create_table", fail)
                with pytest.raises(RuntimeError, match="interruption"):
                    await db.initialize()
            assert await snapshot(db) == before
            async with db.engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0005_agent"
                )
                tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert "memory_entries" not in tables and "automation_runs" not in tables
            await db.initialize()
        finally:
            await db.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["memory", "policy", "run", "background"])
def test_downgrade_refuses_any_phase6_history(settings, kind):
    async def scenario():
        db = Database(settings.database_url)
        try:
            await phase5(db)
            await db.initialize()
            async with db.sessions.begin() as session:
                base = dict(id=str(uuid4()), owner_id="123")
                row = {
                    "memory": lambda: MemoryEntry(
                        **base, kind="preference", content="Synthetic", confirmed_by_owner=True
                    ),
                    "policy": lambda: AutomationPolicy(
                        **base, kind="morning", enabled=False, config_json={}
                    ),
                    "run": lambda: AutomationRun(
                        **base,
                        kind="daily",
                        period_key="2030-01-10",
                        timezone="UTC",
                        scheduled_at=NOW,
                        expires_at=NOW + timedelta(hours=2),
                        policy_version=1,
                    ),
                    "background": lambda: AgentUsage(
                        **base, model="test-model", purpose="background", charged_tokens=10
                    ),
                }[kind]()
                session.add(row)
            with pytest.raises(RuntimeError, match="Refusing to discard"):
                async with db.engine.begin() as connection:
                    await connection.run_sync(lambda conn: migrate(conn, "downgrade", "0005_agent"))
            async with db.engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0007_connections"
                )
                assert await connection.scalar(text("PRAGMA integrity_check")) == "ok"
        finally:
            await db.close()

    asyncio.run(scenario())
