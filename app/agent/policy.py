"""Deterministic time checks for common Vietnamese single-write requests."""

import re
from datetime import timedelta

from app.agent.tool_registry import timestamp
from app.domain.errors import ValidationError
from app.domain.time import parse_local_datetime, zone


def explicit_time(text, now, timezone):
    text = text.lower()
    local = now.astimezone(zone(timezone))
    relative = re.search(r"sau\s+(\d{1,4})\s*(phút|giờ)", text)
    if relative:
        count = int(relative[1])
        if not 1 <= count <= 1440:
            raise ValidationError("Khoảng nhắc tương đối nằm ngoài phạm vi hỗ trợ.")
        return now + timedelta(minutes=count * (60 if relative[2] == "giờ" else 1))
    clock = re.search(r"(?<!\d)(\d{1,2})\s*(?:h|giờ|:)\s*(\d{1,2})?", text)
    if not clock:
        return None
    hour, minute = int(clock[1]), int(clock[2] or 0)
    if hour < 12 and re.search(r"chiều|tối", text):
        hour += 12
    target = local.date()
    full = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    short = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", text)
    if full:
        date_text = full[1]
    elif short:
        date_text = f"{int(short[3] or local.year):04d}-{int(short[2]):02d}-{int(short[1]):02d}"
    else:
        if "ngày kia" in text:
            target += timedelta(days=2)
        elif "mai" in text:
            target += timedelta(days=1)
        weekdays = {"hai": 0, "ba": 1, "tư": 2, "năm": 3, "sáu": 4, "bảy": 5}
        weekday = re.search(r"(?:mỗi|hàng)\s+thứ\s+(hai|ba|tư|năm|sáu|bảy)", text)
        if weekday:
            target += timedelta(days=(weekdays[weekday[1]] - target.weekday()) % 7)
        if re.search(r"(?:mỗi|hàng)\s+chủ nhật", text):
            target += timedelta(days=(6 - target.weekday()) % 7)
        date_text = target.isoformat()
    result = parse_local_datetime(f"{date_text} {hour:02d}:{minute:02d}", timezone)
    if (
        not full
        and not short
        and re.search(r"mỗi|hàng ngày|hằng ngày|hàng tuần", text)
        and result <= now
    ):
        next_date = result.astimezone(zone(timezone)).date() + timedelta(
            days=7 if "thứ" in text or "chủ nhật" in text else 1
        )
        result = parse_local_datetime(f"{next_date} {hour:02d}:{minute:02d}", timezone)
    return result


def validate_write_time(name, args, content, now, timezone):
    field = {
        "create_task": "due_at",
        "create_reminder": "first_fire_at",
        "create_calendar_event": "starts_at",
    }.get(name)
    if not field or args.get(field) is None:
        return
    expected = explicit_time(content, now, timezone)
    if expected and re.search(r"sau\s+\d+\s*(phút|giờ)", content.lower()):
        args[field] = expected.isoformat()
        return
    if expected is None or timestamp(args[field]) != expected:
        raise ValidationError(
            "Ngày giờ tool chưa khớp yêu cầu rõ ràng. "
            "Hỏi lại ngày YYYY-MM-DD, giờ HH:MM theo timezone Settings; không tự đoán."
        )
