"""Strict schemas shared by Responses and the server-side gateway."""

import json
from datetime import date, datetime

from jsonschema import Draft202012Validator

from app.domain.errors import ValidationError
from app.domain.time import as_utc


def obj(**properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def string(nullable=False, **kwargs):
    return {"type": ["string", "null"] if nullable else "string", "maxLength": 250, **kwargs}


ID = string(pattern=r"^[0-9a-f-]{36}$")
OPT_ID = {**ID, "type": ["string", "null"]}
STAMP = string(True, description="ISO8601 with explicit UTC offset, or null if unknown")
PRIORITY = {"type": "string", "enum": ["low", "medium", "high", "critical"]}
TASK = obj(
    title=string(minLength=1),
    due_at=STAMP,
    priority=PRIORITY,
    project_id=OPT_ID,
    estimated_minutes={"type": ["integer", "null"], "minimum": 1, "maximum": 10080},
)
EVENT = obj(
    title=string(minLength=1),
    starts_at=string(),
    ends_at=string(),
    is_fixed={"type": "boolean"},
    task_id=OPT_ID,
)
REMINDER = obj(
    title=string(minLength=1),
    first_fire_at=string(),
    recurrence_type={"type": "string", "enum": ["none", "daily", "weekly"]},
    task_id=OPT_ID,
    event_id=OPT_ID,
)
CHANGE = obj(event_id=ID, starts_at=string(), ends_at=string())
SCHEMAS = {
    "get_today_overview": obj(date=string()),
    "list_tasks": obj(
        status=string(True),
        due_from=STAMP,
        due_to=STAMP,
        project_id=OPT_ID,
        limit={"type": "integer", "minimum": 1, "maximum": 20},
    ),
    "get_task": obj(task_id=ID),
    "list_projects": obj(status=string(True)),
    "list_events": obj(date_from=string(), date_to=string()),
    "find_free_slots": obj(
        date=string(), min_minutes={"type": "integer", "minimum": 1, "maximum": 1440}
    ),
    "list_reminders": obj(status=string(True)),
    "get_preferences": obj(
        keys={
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "timezone",
                    "locale",
                    "workday_start",
                    "workday_end",
                    "quiet_start",
                    "quiet_end",
                ],
            },
            "maxItems": 6,
        }
    ),
    "suggest_next_action": obj(date=string()),
    "create_task": TASK,
    "complete_task": obj(task_id=ID),
    "create_calendar_event": EVENT,
    "create_reminder": REMINDER,
    "propose_reschedule": obj(
        changes={"type": "array", "items": CHANGE, "minItems": 1, "maxItems": 10}
    ),
    "propose_bulk_task_update": obj(
        task_ids={"type": "array", "items": ID, "minItems": 1, "maxItems": 10},
        updates=obj(
            status=string(True),
            priority={
                "type": ["string", "null"],
                "enum": ["low", "medium", "high", "critical", None],
            },
        ),
    ),
}
WRITES = frozenset(
    {
        "create_task",
        "complete_task",
        "create_calendar_event",
        "create_reminder",
        "propose_reschedule",
        "propose_bulk_task_update",
    }
)


def tools(names):
    return [
        {
            "type": "function",
            "name": name,
            "description": (
                "Prepare a preview for owner approval; never execute. "
                if name in WRITES
                else "Read owner data. "
            )
            + name,
            "strict": True,
            "parameters": SCHEMAS[name],
        }
        for name in names
    ]


def validate(name, value):
    if name not in SCHEMAS:
        raise ValidationError("Tool không được cấp quyền.")
    try:
        if isinstance(value, str):
            if len(value) > 12000:
                raise ValueError
            value = json.loads(value)
        if not Draft202012Validator(SCHEMAS[name]).is_valid(value):
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        raise ValidationError("Tham số tool không hợp lệ; cần hỏi lại thông tin.") from None
    return value


def timestamp(value):
    if value is None:
        return None
    try:
        return as_utc(datetime.fromisoformat(value))
    except (ValueError, TypeError):
        raise ValidationError("Cần ngày giờ đầy đủ với múi giờ.") from None


def day(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValidationError("Cần ngày YYYY-MM-DD cụ thể.") from None
