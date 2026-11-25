"""Local Git safety gate: never prints matched content or loads bot/AI clients.

python -m app.security_check --history --staged
Patterns + exact local credentials are useful checks, not a universal secret detector.
"""

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from app.integrations.config import CREDENTIAL_REFS
from app.security import SECRET_PATTERNS, SecretFilter


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    line: int | None = None
    object_id: str | None = None


def forbidden_path(path):
    value = PurePosixPath(path.lower())
    return (
        value.name == ".env"
        or (value.name.startswith(".env.") and value.name != ".env.example")
        or value.suffix
        in {
            ".db",
            ".sqlite",
            ".sqlite3",
            ".pem",
            ".key",
            ".p12",
            ".pfx",
            ".log",
            ".dump",
            ".backup",
        }
        or value.name.endswith((".db.bak", ".sql.gz", ".sql", ".env"))
        or bool({"backups", "logs", ".venv", "__pycache__"} & set(value.parts))
    )


def scan_data(path, data, *, secrets=(), object_id=None):
    findings = []
    guard = SecretFilter(secrets)
    if guard.contains(path):
        findings.append(Finding(guard.redact(path), "credential_in_path", object_id=object_id))
    path = guard.redact(path)
    if forbidden_path(path):
        findings.append(Finding(path, "sensitive_path", object_id=object_id))
    if data.startswith(b"SQLite format 3\x00"):
        findings.append(Finding(path, "sqlite_content", object_id=object_id))
    text = data.decode("utf-8", errors="replace")
    for name, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append(Finding(path, name, text.count("\n", 0, match.start()) + 1, object_id))
    for secret in secrets:
        if secret and secret in text:
            findings.append(
                Finding(
                    path, "local_credential", text.count("\n", 0, text.index(secret)) + 1, object_id
                )
            )
    return findings


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def local_secrets(root):
    """Only for exact comparison. Never include these values in findings/errors."""
    values = {}
    names = {"DISCORD_TOKEN", "OPENAI_API_KEY", *CREDENTIAL_REFS.values()}
    path = root / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() in names:
                values[name.strip()] = value.strip().strip("\"'")
    for name in names:
        if name in os.environ:
            values[name] = os.environ[name]
    return tuple(v for v in values.values() if len(v) >= 20 and "replace" not in v)


def scan_repository(root, *, history=False, staged=False):
    root = Path(root).resolve()
    secrets = local_secrets(root)
    findings, scanned = [], set()
    paths = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\x00")
    for raw_path in set(paths) - {b""}:
        path = raw_path.decode("utf-8")
        target = root / path
        if target.is_symlink():
            findings.append(Finding(path, "symlink_not_scanned"))
        elif target.is_file():
            findings.extend(scan_data(path, target.read_bytes(), secrets=secrets))
    objects = {}
    if history:
        for line in git(root, "rev-list", "--objects", "--all").splitlines():
            oid, _, path = line.partition(b" ")
            objects.setdefault(oid.decode(), set()).add(path.decode("utf-8", "replace"))
        # Inspect every path in historical trees too: one blob may have multiple names.
        for revision in git(root, "rev-list", "--all").splitlines():
            for entry in git(root, "ls-tree", "-rz", revision.decode()).split(b"\x00"):
                if not entry:
                    continue
                header, path = entry.split(b"\t", 1)
                _, kind, oid = header.split()
                if kind == b"blob" and forbidden_path(path.decode("utf-8", "replace")):
                    findings.append(
                        Finding(
                            path.decode("utf-8", "replace"),
                            "sensitive_history_path",
                            object_id=oid.decode()[:12],
                        )
                    )
    if staged:
        for entry in git(root, "ls-files", "--stage", "-z").split(b"\x00"):
            if not entry:
                continue
            header, path = entry.split(b"\t", 1)
            mode, oid, stage = header.split()
            name = path.decode("utf-8", "replace")
            if mode == b"120000":
                findings.append(Finding(name, "staged_symlink"))
            if stage != b"0":
                findings.append(Finding(name, "unmerged_index"))
            objects.setdefault(oid.decode(), set()).add(name)
    for oid, paths in objects.items():
        if git(root, "cat-file", "-t", oid).strip() != b"blob":
            continue
        data = git(root, "cat-file", "blob", oid)
        scanned.add(oid)
        for path in paths:
            findings.extend(scan_data(path, data, secrets=secrets, object_id=oid[:12]))
    return sorted(
        set(findings), key=lambda item: (item.path, item.rule, item.line or 0, item.object_id or "")
    ), len(scanned)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="All locally reachable refs")
    parser.add_argument(
        "--staged", action="store_true", help="Scan index blobs, not only working tree"
    )
    options = parser.parse_args(argv)
    try:
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
        findings, blobs = scan_repository(root, history=options.history, staged=options.staged)
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("Security check could not finish; no content printed. Do not treat as passed.")
        return 2
    print(
        json.dumps(
            {
                "reachable_blobs_scanned": blobs,
                "findings": SecretFilter(local_secrets(root)).redact(
                    [asdict(item) for item in findings]
                ),
            },
            ensure_ascii=True,
        )
    )
    if findings:
        print("BLOCKED: review reported paths/rules. No matched values are printed.")
        return 1
    print(
        "PASS: checked working tree/index/local history as requested; patterns are not exhaustive."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
