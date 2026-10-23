import os
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

from app.config import PROJECT_ROOT
from app.db.backup import backup_database


def test_backup_includes_committed_wal_without_modifying_source_and_restores(tmp_path):
    source = tmp_path / "wal.db"
    with closing(sqlite3.connect(source)) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('synthetic test value')")
        connection.commit()
        before = source.read_bytes()
        backup = backup_database(source, tmp_path / "backups" / "snapshot.db")
        assert source.read_bytes() == before
        with closing(sqlite3.connect(backup)) as snapshot:
            assert snapshot.execute("SELECT value FROM sample").fetchall() == [
                ("synthetic test value",)
            ]
            assert snapshot.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        if os.name == "posix":
            assert backup.stat().st_mode & 0o777 == 0o600
    restored = backup_database(backup, tmp_path / "restored.db")
    with closing(sqlite3.connect(restored)) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == (
            "synthetic test value",
        )


def test_backup_refuses_missing_source_same_path_and_existing_destination(tmp_path):
    source, destination = tmp_path / "source.db", tmp_path / "backup.db"
    with pytest.raises(FileNotFoundError):
        backup_database(source, destination)
    assert not source.exists() and not destination.exists()
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
    with pytest.raises(ValueError):
        backup_database(source, source)
    destination.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        backup_database(source, destination)
    assert destination.read_bytes() == b"keep me"


def test_invalid_source_leaves_no_successful_backup(tmp_path):
    source, destination = tmp_path / "invalid.db", tmp_path / "backup.db"
    source.write_bytes(b"invalid database")
    with pytest.raises(sqlite3.DatabaseError):
        backup_database(source, destination)
    assert not destination.exists()


def test_backup_cli_uses_configured_path_without_discord_credentials(tmp_path):
    source, destination = tmp_path / "source.db", tmp_path / "backup.db"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{source}",
        "DISCORD_TOKEN": "",
        "DISCORD_OWNER_ID": "",
    }
    for expected in (0, 1):
        result = subprocess.run(
            [sys.executable, "-m", "app.db.backup", "--output", str(destination)],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == expected
        assert "DISCORD_TOKEN" not in result.stdout + result.stderr
    assert destination.exists()
