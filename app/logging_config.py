"""JSON operational logs without exception payloads or message contents."""

import json
import logging
from datetime import UTC, datetime


class SafeJsonFormatter(logging.Formatter):
    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in ("interaction_id", "error_type", "command_count"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        # Tracebacks may contain HTTP URLs, SQL parameters, or private message text.
        if record.exc_info and record.exc_info[0]:
            payload["error_type"] = record.exc_info[0].__name__
        result = json.dumps(payload, ensure_ascii=False)
        for secret in self._secrets:
            escaped_secret = json.dumps(secret, ensure_ascii=False)[1:-1]
            result = result.replace(escaped_secret, "[REDACTED]")
        return result


def configure_logging(level: str, token: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter((token,)))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # SDK debug/error payloads can contain raw Gateway messages or SQL values.
    # NOVA's own handlers report safe error classes and lifecycle events instead.
    for name in ("discord", "sqlalchemy", "aiosqlite"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    logging.getLogger("alembic").setLevel(logging.WARNING)
