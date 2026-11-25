import asyncio
from uuid import uuid4

import pytest
from alembic.operations import Operations
from sqlalchemy import insert, inspect, text
from sqlalchemy.exc import IntegrityError
from test_agent import bundle
from test_connections import ARGS
from test_personal_migration import phase5
from test_reminder_dispatch_migration import migrate

from app.db.backup import backup_database
from app.db.models import IntegrationConnection
from app.db.session import Database


async def phase6(db):
    await phase5(db)
    async with db.engine.begin() as connection:
        await connection.run_sync(lambda conn: migrate(conn, "upgrade", "0006_personal"))


async def snapshot(db):
    async with db.engine.connect() as connection:
        tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        return {
            table: (await connection.execute(text(f'SELECT * FROM "{table}" ORDER BY rowid'))).all()
            for table in tables
            if table not in {"alembic_version", "integration_connections"}
        }


def test_7a1_upgrade_copy_restore_empty_downgrade_preserves_every_legacy_row(settings, tmp_path):
    async def scenario():
        db = Database(settings.database_url)
        try:
            await phase6(db)
            before = await snapshot(db)
        finally:
            await db.close()
        backup = backup_database(tmp_path / "nova.db", tmp_path / "before7.db")
        copy = backup_database(backup, tmp_path / "upgrade7.db")
        upgraded = Database(f"sqlite+aiosqlite:///{copy}")
        try:
            await upgraded.initialize()
            await upgraded.initialize()
            assert await snapshot(upgraded) == before
            async with upgraded.engine.begin() as connection:
                assert await connection.scalar(text("PRAGMA integrity_check")) == "ok"
                assert not (await connection.execute(text("PRAGMA foreign_key_check"))).all()
                await connection.run_sync(lambda conn: migrate(conn, "downgrade", "0006_personal"))
            assert await snapshot(upgraded) == before
        finally:
            await upgraded.close()
        restored = backup_database(backup, tmp_path / "restored.db")
        recovered = Database(f"sqlite+aiosqlite:///{restored}")
        try:
            assert await snapshot(recovered) == before
        finally:
            await recovered.close()

    asyncio.run(scenario())


def test_interruption_rolls_back_new_table_and_revision(settings, monkeypatch):
    async def scenario():
        db = Database(settings.database_url)
        try:
            await phase6(db)
            before = await snapshot(db)
            create = Operations.create_table

            def fail(op, name, *args, **kwargs):
                result = create(op, name, *args, **kwargs)
                if name == "integration_connections":
                    raise RuntimeError("synthetic interruption")
                return result

            with monkeypatch.context() as patcher:
                patcher.setattr(Operations, "create_table", fail)
                with pytest.raises(RuntimeError, match="interruption"):
                    await db.initialize()
            assert await snapshot(db) == before
            async with db.engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0006_personal"
                )
                assert "integration_connections" not in await connection.run_sync(
                    lambda conn: inspect(conn).get_table_names()
                )
        finally:
            await db.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("status", ["configured", "disconnected"])
def test_downgrade_refuses_any_connection_history(settings, status):
    async def scenario():
        db = Database(settings.database_url)
        try:
            await phase6(db)
            await db.initialize()
            async with db.sessions.begin() as session:
                session.add(
                    IntegrationConnection(
                        id=str(uuid4()),
                        owner_id="123",
                        provider="github",
                        label="Work",
                        credential_ref="GITHUB_READ_TOKEN",
                        status=status,
                        resources_json=["owner/repo"],
                        requested_permissions_json=["read"],
                    )
                )
            with pytest.raises(RuntimeError, match="Refusing to discard"):
                async with db.engine.begin() as connection:
                    await connection.run_sync(
                        lambda conn: migrate(conn, "downgrade", "0006_personal")
                    )
            async with db.engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0007_connections"
                )
                assert (
                    await connection.scalar(text("SELECT count(*) FROM integration_connections"))
                    == 1
                )
        finally:
            await db.close()

    asyncio.run(scenario())


def test_downgrade_refuses_unexecuted_connection_proposal(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = bundle(env)
            await pending.propose(env.owner, "configure_connection", ARGS, turn="migration-history")
            assert (await core.connections.list(env.owner))["total"] == 0
            with pytest.raises(RuntimeError, match="orphan connection approval history"):
                async with env.database.engine.begin() as connection:
                    await connection.run_sync(
                        lambda conn: migrate(conn, "downgrade", "0006_personal")
                    )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "changes",
    [
        dict(owner_id="999"),
        dict(provider="unknown"),
        dict(status="enabled"),
        dict(credential_ref="DISCORD_TOKEN"),
        dict(version=0),
        dict(label=" "),
    ],
)
def test_database_rejects_invalid_connection_owner_and_metadata(core_factory, changes):
    async def scenario():
        async with core_factory() as env:
            values = dict(
                id=str(uuid4()),
                owner_id=str(env.owner),
                provider="github",
                label="Work",
                credential_ref="GITHUB_READ_TOKEN",
                status="configured",
                version=1,
                resources_json=["owner/repo"],
                requested_permissions_json=["read"],
            )
            with pytest.raises(IntegrityError):
                async with env.database.sessions.begin() as session:
                    # Core insert tests the DB checks without ORM version initialization.
                    await session.execute(
                        insert(IntegrationConnection).values(**(values | changes))
                    )

    asyncio.run(scenario())
