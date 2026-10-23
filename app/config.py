"""Validated configuration. Never include environment values in error messages."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./nova.db"


class ConfigurationError(ValueError):
    """A safe, user-facing configuration error."""


def validate_discord_id(value: str, name: str) -> int:
    if not re.fullmatch(r"[0-9]{1,20}", value) or not 0 < int(value) < 2**64:
        raise ConfigurationError(f"{name} phải là Discord user/server ID hợp lệ.")
    return int(value)


def environment(env_file: Path | None = None) -> dict[str, str]:
    """Process environment wins over .env; do not expand untrusted substitutions."""
    values = dotenv_values(env_file or PROJECT_ROOT / ".env", interpolate=False)
    return {**{key: value for key, value in values.items() if value is not None}, **os.environ}


def database_url_from_mapping(values: Mapping[str, str]) -> str:
    raw = values.get("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    try:
        url = make_url(raw)
    except (ArgumentError, ValueError):
        raise ConfigurationError("DATABASE_URL không hợp lệ.") from None
    if (
        url.drivername != "sqlite+aiosqlite"
        or not url.database
        or url.database == ":memory:"
        or url.host
        or url.username
        or url.password
        or url.query
        or "\x00" in url.database
    ):
        raise ConfigurationError("DATABASE_URL phải trỏ tới file SQLite dùng sqlite+aiosqlite.")
    path = Path(url.database).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return url.set(database=str(path.resolve())).render_as_string(hide_password=False)


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str = field(repr=False)
    owner_id: int
    database_url: str = field(repr=False)
    timezone: str
    log_level: str = "INFO"
    guild_id: int | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "Settings":
        token = values.get("DISCORD_TOKEN", "").strip()
        if not token or token == "replace-me" or any(char.isspace() for char in token):
            raise ConfigurationError("DISCORD_TOKEN bắt buộc; hãy điền bot token trong .env.")
        owner_id = validate_discord_id(
            values.get("DISCORD_OWNER_ID", "").strip(), "DISCORD_OWNER_ID"
        )
        timezone = values.get("TIMEZONE", "Asia/Ho_Chi_Minh").strip()
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ConfigurationError("TIMEZONE phải là tên múi giờ IANA hợp lệ.") from None
        level = values.get("LOG_LEVEL", "INFO").strip().upper()
        if level not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError("LOG_LEVEL phải là INFO, WARNING, ERROR hoặc CRITICAL.")
        guild = values.get("DISCORD_GUILD_ID", "").strip()
        return cls(
            discord_token=token,
            owner_id=owner_id,
            database_url=database_url_from_mapping(values),
            timezone=timezone,
            log_level=level,
            guild_id=validate_discord_id(guild, "DISCORD_GUILD_ID") if guild else None,
        )


def load_settings(env_file: Path | None = None) -> Settings:
    return Settings.from_mapping(environment(env_file))
