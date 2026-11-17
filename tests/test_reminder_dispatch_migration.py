import asyncio
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from sqlalchemy import inspect, text

from app.config import PROJECT_ROOT
from app.db.session import Database


def migrate(connection, direction, revision):
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.attributes["connection"] = connection
    getattr(command, direction)(config, revision)


async def seed_4a(database):
    async with database.engine.begin() as connection:
        await connection.run_sync(lambda conn: migrate(conn, "upgrade", "0003_reminders"))
        stamp, reminder, delivery = "2026-10-25 13:00:00.000000", str(uuid4()), str(uuid4())
        await connection.execute(
            text("INSERT INTO users VALUES ('123', 'UTC', 'vi-VN', :stamp)"), {"stamp": stamp}
        )
        await connection.execute(
            text(
                "INSERT INTO reminders (id, owner_id, title, next_fire_at, created_at, updated_at) "
                "VALUES (:id, '123', 'Synthetic 4A', :stamp, :stamp, :stamp)"
            ),
            {"id": reminder, "stamp": stamp},
        )
        await connection.execute(
            text(
                "INSERT INTO reminder_deliveries (id, reminder_id, scheduled_fire_at) "
                "VALUES (:id, :reminder, :stamp)"
            ),
            {"id": delivery, "reminder": reminder, "stamp": stamp},
        )


def test_upgrade_4a_delivery_rows_are_preserved_and_metadata_is_nullable(settings):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed_4a(database)
            async with database.engine.connect() as connection:
                before = (
                    await connection.execute(
                        text(
                            "SELECT id, reminder_id, scheduled_fire_at, status, attempt_count "
                            "FROM reminder_deliveries"
                        )
                    )
                ).all()
            await database.initialize()
            async with database.engine.connect() as connection:
                after = (
                    await connection.execute(
                        text(
                            "SELECT id, reminder_id, scheduled_fire_at, status, attempt_count "
                            "FROM reminder_deliveries"
                        )
                    )
                ).all()
                assert after == before
                assert (
                    await connection.execute(
                        text(
                            "SELECT retry_at, claim_token, acknowledged_at, finished_reason "
                            "FROM reminder_deliveries"
                        )
                    )
                ).one() == (None, None, None, None)
                assert (await connection.execute(text("PRAGMA foreign_key_check"))).all() == []
            with pytest.raises(RuntimeError, match="lịch sử delivery"):
                async with database.engine.begin() as connection:
                    await connection.run_sync(
                        lambda conn: migrate(conn, "downgrade", "0003_reminders")
                    )
        finally:
            await database.close()

    asyncio.run(scenario())


def test_interrupted_dispatch_metadata_upgrade_rolls_back_partial_columns(settings, monkeypatch):
    add_column = Operations.add_column

    def interrupted(operations, table, column, *args, **kwargs):
        result = add_column(operations, table, column, *args, **kwargs)
        if column.name == "finished_reason":
            raise RuntimeError("synthetic interrupted metadata upgrade")
        return result

    async def scenario():
        database = Database(settings.database_url)
        try:
            await seed_4a(database)
            with monkeypatch.context() as patcher:
                patcher.setattr(Operations, "add_column", interrupted)
                with pytest.raises(RuntimeError, match="interrupted metadata"):
                    await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0003_reminders"
                )
                columns = await connection.run_sync(
                    lambda conn: inspect(conn).get_columns("reminder_deliveries")
                )
                assert "retry_at" not in {column["name"] for column in columns}
                assert (
                    await connection.scalar(text("SELECT count(*) FROM reminder_deliveries")) == 1
                )
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(scenario())
