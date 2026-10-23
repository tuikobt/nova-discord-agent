"""One async engine per process; schema changes always run through Alembic."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import PROJECT_ROOT


def upgrade_schema(connection: Connection) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


class Database:
    def __init__(self, url: str) -> None:
        path = make_url(url).database
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(url, echo=False, hide_parameters=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        @event.listens_for(self.engine.sync_engine, "connect")
        def sqlite_pragmas(dbapi_connection, connection_record) -> None:
            # Let SQLAlchemy issue BEGIN for DDL as well as DML. SQLite's
            # legacy mode would otherwise commit each migration DDL separately.
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()

        @event.listens_for(self.engine.sync_engine, "begin")
        def sqlite_begin(connection: Connection) -> None:
            connection.exec_driver_sql("BEGIN")

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(upgrade_schema)

    async def close(self) -> None:
        await self.engine.dispose()
