"""Strict local wall-clock parsing and UTC conversion; no natural-language guesses."""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.errors import ValidationError

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise ValidationError("Múi giờ IANA không hợp lệ.") from None


def as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("Thời gian phải có ngày, giờ và timezone rõ ràng.")
    try:
        return value.astimezone(UTC)
    except (ValueError, OverflowError):
        raise ValidationError("Thời gian nằm ngoài phạm vi hỗ trợ.") from None


def parse_local_datetime(value: str, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", value):
        raise ValidationError("Nhập thời gian theo YYYY-MM-DD HH:MM, ví dụ 2026-10-25 20:00.")
    try:
        local = datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValidationError("Ngày hoặc giờ không hợp lệ.") from None
    timezone_info = zone(timezone)
    candidates = set()
    for fold in (0, 1):
        utc_value = as_utc(local.replace(tzinfo=timezone_info, fold=fold))
        if utc_value.astimezone(timezone_info).replace(tzinfo=None) == local:
            candidates.add(utc_value)
    if len(candidates) != 1:
        raise ValidationError(
            "Giờ local không tồn tại hoặc có hai offset; cần thời gian có offset rõ."
        )
    return candidates.pop()


def format_local_datetime(value: datetime, timezone: str = DEFAULT_TIMEZONE) -> str:
    try:
        return f"{as_utc(value).astimezone(zone(timezone)):%Y-%m-%d %H:%M} ({timezone})"
    except (OverflowError, ValueError) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError("Thời gian nằm ngoài phạm vi hỗ trợ.") from None
