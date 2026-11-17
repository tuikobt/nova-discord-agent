"""Read-only runtime checks before starting NOVA against an existing database."""

import io
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from app.config import (
    PROJECT_ROOT,
    ConfigurationError,
    Settings,
    database_url_from_mapping,
    environment,
)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    message: str


def inspect_runtime(values) -> tuple[Check, ...]:
    checks = []
    settings = None
    try:
        settings = Settings.from_mapping(values)
        checks.append(Check("config", True, "Required configuration is valid; secrets hidden."))
    except ConfigurationError as error:
        field = next(
            (
                name
                for name in (
                    "DISCORD_TOKEN",
                    "DISCORD_OWNER_ID",
                    "DATABASE_URL",
                    "TIMEZONE",
                    "LOG_LEVEL",
                    "DISCORD_GUILD_ID",
                )
                if name in str(error)
            ),
            "Configuration",
        )
        checks.append(Check("config", False, f"{field} is missing or invalid; edit .env locally."))

    try:
        path = Path(make_url(database_url_from_mapping(values)).database)
    except ConfigurationError:
        checks.append(Check("database", False, "DATABASE_URL is invalid; no database opened."))
        return tuple(checks)
    if not path.is_file():
        checks.append(
            Check("database", False, "Existing database not found; no replacement created.")
        )
        return tuple(checks)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    known = {revision.revision for revision in scripts.walk_revisions()}
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            checks.append(
                Check(
                    "integrity",
                    connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
                    "SQLite integrity check.",
                )
            )
            foreign_ok = not connection.execute("PRAGMA foreign_key_check").fetchall()
            checks.append(Check("foreign_keys", foreign_ok, "No orphan references."))
            versions = connection.execute("SELECT version_num FROM alembic_version").fetchall()
            current = versions[0][0] if len(versions) == 1 else None
            schema_ok = len(heads) == 1 and current == heads[0]
            message = (
                "Schema is at the source head."
                if schema_ok
                else "Backup and migrate the existing database before starting."
                if current in known
                else "Unknown or missing revision; do not stamp/reset the database."
            )
            checks.append(Check("revision", schema_ok, message))
            if settings is not None:
                owners = connection.execute("SELECT discord_user_id FROM users").fetchall()
                expected = str(settings.owner_id)
                owner_ok = owners == [(expected,)]
                checks.append(
                    Check("owner", owner_ok, "Database owner must match configured owner.")
                )
                has_settings = (
                    connection.execute(
                        "SELECT 1 FROM user_settings WHERE owner_id = ?", (expected,)
                    ).fetchone()
                    is not None
                )
                checks.append(Check("settings", has_settings, "Owner settings exist."))
    except sqlite3.Error:
        checks.append(
            Check(
                "database", False, "Cannot validate existing schema; keep the database unchanged."
            )
        )
    return tuple(checks)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    checks = inspect_runtime(environment())
    for check in checks:
        print(f"{'OK' if check.ok else 'BLOCKED'} [{check.name}] {check.message}")
    print("Read-only checks only; Discord connectivity and live delivery are not verified.")
    return 0 if all(check.ok for check in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
