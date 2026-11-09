"""SQLite snapshot without Discord credentials: python -m app.db.backup --output PATH."""

import argparse
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import database_url_from_mapping, environment


def backup_database(source: Path, destination: Path) -> Path:
    """Copy a consistent SQLite snapshot (including WAL); never overwrite a file."""
    source, destination = source.resolve(), destination.resolve()
    if not source.is_file():
        raise FileNotFoundError("Không tìm thấy file database nguồn.")
    if source == destination:
        raise ValueError("Backup phải khác file nguồn.")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Reserve exclusively; restrictive permissions on POSIX, directory ACLs on Windows.
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(destination)) as snapshot:
                original.backup(snapshot, pages=256)
                if snapshot.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Backup không vượt qua kiểm tra integrity.")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Sao lưu SQLite NOVA, không ghi đè file đã có.")
    parser.add_argument("--output", required=True, type=Path, help="File backup riêng tư mới")
    args = parser.parse_args()
    try:
        url = database_url_from_mapping(environment())
        source = Path(make_url(url).database)
        destination = backup_database(source, args.output)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Backup thất bại ({type(error).__name__}); chưa chạy migration.", file=sys.stderr)
        return 1
    print(f"Backup đã kiểm tra integrity: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
