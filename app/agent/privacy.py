"""Minimize model-visible fields and keep internal instructions out of DM output."""

import re
import unicodedata

from app.agent.serialization import plain
from app.security import SecretFilter

INTERNAL_REPLY = (
    "Tôi có thể giải thích các chức năng của NOVA, nhưng không hiển thị hướng dẫn nội bộ."
)


def normalized(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def requests_instructions(text):
    value = normalized(text)
    target = re.search(
        r"system prompt|developer (?:prompt|message)|internal (?:prompt|instructions)"
        r"|hidden (?:prompt|instructions)|original prompt|prompt (?:gốc|hệ thống|nội bộ)"
        r"|(?:hướng dẫn|chỉ dẫn|chỉ thị) (?:hệ thống|nội bộ)|instructions above",
        value,
    )
    verb = re.search(
        r"show|reveal|repeat|print|display|dump|translate|quote|return|xuất|in|hiện|lộ"
        r"|nhắc lại|chép|dịch|đọc|cho (?:tôi|mình) xem",
        value,
    )
    return bool(target and verb)


def safe_model_text(text, instructions, secrets):
    """Best-effort echo check; prompts contain no credentials in the first place."""
    source = normalized(instructions).split()
    rendered = normalized(text)
    if any(" ".join(source[i : i + 12]) in rendered for i in range(max(0, len(source) - 11))):
        return INTERNAL_REPLY
    return secrets.redact(text)


TASK_FIELDS = {"id", "title", "status", "priority", "project_id", "estimated_minutes", "due_at"}
EVENT_FIELDS = {"id", "title", "starts_at", "ends_at", "status", "is_fixed", "task_id"}
PROJECT_FIELDS = {"id", "name", "status", "deadline_at"}
REMINDER_FIELDS = {
    "id",
    "title",
    "next_fire_at",
    "recurrence_type",
    "recurrence",
    "status",
    "task_id",
    "event_id",
}


def fields(value, allowed):
    return {key: item for key, item in value.items() if key in allowed}


def model_result(name, value, secrets=None):
    value = plain(value)
    if name == "get_task":
        value = fields(value, TASK_FIELDS | {"description", "completed_at"})
    elif name in {"list_tasks", "list_projects", "list_events", "list_reminders"}:
        allowed = {
            "list_tasks": TASK_FIELDS,
            "list_projects": PROJECT_FIELDS,
            "list_events": EVENT_FIELDS,
            "list_reminders": REMINDER_FIELDS,
        }[name]
        value = {
            **fields(value, {"total", "page", "page_size"}),
            "items": [fields(item, allowed) for item in value["items"]],
        }
    elif name in {"get_today_overview", "suggest_next_action"}:
        value["tasks"] = [fields(item, TASK_FIELDS) for item in value["tasks"]]
        value["events"] = {
            **fields(value["events"], {"total", "page", "page_size"}),
            "items": [fields(item, EVENT_FIELDS) for item in value["events"]["items"]],
        }
    return (secrets or SecretFilter()).redact(value)
