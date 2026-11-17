import asyncio
import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy.engine import make_url

from app.db.session import Database
from app.domain.authorization import OwnerAuthorization
from app.preflight import inspect_runtime
from app.preflight import main as preflight_main
from app.services.settings_service import SettingsService


def test_missing_database_and_credentials_do_not_create_files_or_reveal_tokens(tmp_path):
    path = tmp_path / "missing" / "nova.db"
    results = inspect_runtime({"DATABASE_URL": f"sqlite+aiosqlite:///{path}"})
    assert {item.name for item in results if not item.ok} == {"config", "database"}
    assert not path.parent.exists()


def test_preflight_checks_existing_owner_schema_and_integrity_without_changing_data(
    settings, env_values
):
    async def seed():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            await SettingsService(
                database.sessions, OwnerAuthorization(settings.owner_id)
            ).initialize_owner(settings.owner_id, settings.timezone)
        finally:
            await database.close()

    asyncio.run(seed())
    path = Path(make_url(settings.database_url).database)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    results = inspect_runtime(env_values)
    assert all(item.ok for item in results)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert env_values["DISCORD_TOKEN"] not in repr(results)
    different = {**env_values, "DISCORD_OWNER_ID": str(settings.owner_id + 1)}
    assert not next(item.ok for item in inspect_runtime(different) if item.name == "owner")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_unknown_revision_missing_settings_and_foreign_key_damage_fail_closed(settings, env_values):
    async def seed():
        database = Database(settings.database_url)
        try:
            await database.initialize()
        finally:
            await database.close()

    asyncio.run(seed())
    path = Path(make_url(settings.database_url).database)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("UPDATE alembic_version SET version_num = ?", ("private-unknown-value",))
        connection.execute(
            "INSERT INTO user_settings (owner_id, updated_at) VALUES ('999', '2026-11-15 00:00:00')"
        )
        connection.commit()
    results = inspect_runtime(env_values)
    assert not next(item.ok for item in results if item.name == "revision")
    assert not next(item.ok for item in results if item.name == "foreign_keys")
    assert not next(item.ok for item in results if item.name == "settings")
    assert "private-unknown-value" not in repr(results)


def test_invalid_database_file_and_invalid_config_are_reported_without_private_payload(tmp_path):
    path = tmp_path / "invalid.db"
    path.write_bytes(b"private-invalid-data")
    results = inspect_runtime(
        {"DATABASE_URL": f"sqlite+aiosqlite:///{path}", "DISCORD_TOKEN": "private-token"}
    )
    assert not all(item.ok for item in results)
    assert "private-token" not in repr(results) and "private-invalid-data" not in repr(results)
    invalid = inspect_runtime({"DATABASE_URL": "postgresql://user:private-password@host/db"})
    assert "private-password" not in repr(invalid)


def test_cli_reports_missing_configuration_and_returns_blocked_without_exposing_values(
    tmp_path, monkeypatch, capsys
):
    values = {
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'missing.db'}",
        "DISCORD_TOKEN": "private-test-token",
    }
    monkeypatch.setattr("app.preflight.environment", lambda: values)
    assert preflight_main() == 2
    output = capsys.readouterr().out
    assert "BLOCKED [config] DISCORD_OWNER_ID" in output
    assert "private-test-token" not in output
    assert not (tmp_path / "missing.db").exists()


def test_cli_returns_success_only_for_valid_existing_runtime(
    settings, env_values, monkeypatch, capsys
):
    async def seed():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            await SettingsService(
                database.sessions, OwnerAuthorization(settings.owner_id)
            ).initialize_owner(settings.owner_id, settings.timezone)
        finally:
            await database.close()

    asyncio.run(seed())
    monkeypatch.setattr("app.preflight.environment", lambda: env_values)
    assert preflight_main() == 0
    output = capsys.readouterr().out
    assert "BLOCKED" not in output and "OK [owner]" in output
    assert "live delivery are not verified" in output
    assert env_values["DISCORD_TOKEN"] not in output
