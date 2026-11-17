"""JSON operational logs without exception payloads or message contents."""

import json
import logging
from datetime import UTC, datetime

from app.security import SecretFilter


class SafeJsonFormatter(logging.Formatter):
    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)
        self._filter = SecretFilter(self._secrets)

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in (
            "interaction_id",
            "error_type",
            "command_count",
            "delivery_id",
            "error_code",
            "attempt_count",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        # Tracebacks may contain HTTP URLs, SQL parameters, or private message text.
        if record.exc_info and record.exc_info[0]:
            payload["error_type"] = record.exc_info[0].__name__
        # Redact before JSON encoding so multiline key material cannot truncate JSON.
        return json.dumps(self._filter.redact(payload), ensure_ascii=False)


def configure_logging(level: str, token: str, api_key: str = "") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter((token, api_key)))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # SDK debug/error payloads can contain raw Gateway messages or SQL values.
    # NOVA's own handlers report safe error classes and lifecycle events instead.
    for name in (
        "discord",
        "sqlalchemy",
        "aiosqlite",
        "openai",
        "httpx",
        "httpx2",
        "httpcore",
        "httpcore2",
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    logging.getLogger("alembic").setLevel(logging.WARNING)
