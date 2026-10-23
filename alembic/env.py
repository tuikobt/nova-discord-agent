"""Async CLI migrations and connection sharing with application bootstrap."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from app.config import database_url_from_mapping, environment
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import Database

config = context.config
target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    database = Database(database_url_from_mapping(environment()))
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await database.close()


if context.is_offline_mode():
    context.configure(
        url=database_url_from_mapping(environment()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif (connection := config.attributes.get("connection")) is not None:
    do_run_migrations(connection)
else:
    asyncio.run(run_async_migrations())
