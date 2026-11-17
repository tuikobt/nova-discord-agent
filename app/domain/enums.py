"""Persisted lowercase values; changes require an Alembic migration."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskStatus(StrEnum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class EventOrigin(StrEnum):
    MANUAL = "manual"
    AGENT = "agent"
    INTEGRATION = "integration"


class RecurrenceType(StrEnum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"


class ReminderStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DONE = "done"
    CANCELLED = "cancelled"


class DeliveryTarget(StrEnum):
    DM = "dm"
    CHANNEL = "channel"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SENT = "sent"
    FAILED = "failed"


class DeliveryKind(StrEnum):
    SCHEDULED = "scheduled"
    SNOOZE = "snooze"


class DeliveryErrorCode(StrEnum):
    """Store classified codes, never exception text or Discord response bodies."""

    FORBIDDEN = "forbidden"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    UNKNOWN_ERROR = "unknown_error"
