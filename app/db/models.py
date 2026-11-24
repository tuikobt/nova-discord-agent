"""Foundation, core management and Phase 4A reminder persistence."""

from __future__ import annotations

from datetime import datetime, time
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    and_,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base, UTCDateTime, utc_now
from app.domain.enums import (
    DeliveryErrorCode,
    DeliveryKind,
    DeliveryStatus,
    DeliveryTarget,
    EventOrigin,
    EventStatus,
    ProjectStatus,
    RecurrenceType,
    ReminderStatus,
    TaskPriority,
    TaskStatus,
)
from app.domain.reminders import RecurrenceRule, ReminderData, discord_id


class PendingAction(Base):
    __tablename__ = "pending_actions"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_pending_owner_key"),
        CheckConstraint("status IN ('pending','rejected','expired','executed')", name="status"),
        Index("ix_pending_owner_expiry", "owner_id", "expires_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(24), ForeignKey("users.discord_user_id"))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    channel_id: Mapped[str | None] = mapped_column(String(24))
    message_id: Mapped[str | None] = mapped_column(String(24))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class AgentUsage(Base):
    __tablename__ = "agent_usage"
    __table_args__ = (
        CheckConstraint(
            "charged_tokens >= 0 AND input_tokens >= 0 AND output_tokens >= 0", name="tokens"
        ),
        Index("ix_agent_usage_owner_created", "owner_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(24), ForeignKey("users.discord_user_id"))
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(20), default="dm", server_default="dm", nullable=False
    )
    charged_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    settled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class User(Base):
    __tablename__ = "users"

    discord_user_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), default="vi-VN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    __table_args__ = (
        CheckConstraint("kind IN ('preference','routine','profile')", name="kind"),
        CheckConstraint("version > 0", name="version"),
        Index("ix_memory_owner_active", "owner_id", "is_deleted", "use_for_ai"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("users.discord_user_id"), nullable=False
    )
    content: Mapped[str | None] = mapped_column(String(1000))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str | None] = mapped_column(String(128))
    confirmed_by_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    use_for_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AutomationPolicy(Base):
    __tablename__ = "automation_policies"
    __table_args__ = (
        UniqueConstraint("owner_id", "kind", name="uq_automation_policy_owner_kind"),
        CheckConstraint("kind IN ('preferences','morning','daily','weekly')", name="kind"),
        CheckConstraint("version > 0", name="version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("users.discord_user_id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "kind", "period_key", name="uq_automation_run_period"),
        CheckConstraint("kind IN ('morning','daily','weekly')", name="kind"),
        CheckConstraint("status IN ('pending','claimed','sent','failed','skipped')", name="status"),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
        Index("ix_automation_run_due", "status", "scheduled_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("users.discord_user_id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    period_key: Mapped[str] = mapped_column(String(10), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claim_token: Mapped[str | None] = mapped_column(String(36))
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(30))
    discord_message_id: Mapped[str | None] = mapped_column(String(24))
    channel_id: Mapped[str | None] = mapped_column(String(24))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    owner_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("users.discord_user_id", ondelete="CASCADE"), primary_key=True
    )
    # Unconfigured local wall-clock preferences; no automation is enabled in P1.
    morning_briefing_time: Mapped[time | None] = mapped_column(Time)
    daily_review_time: Mapped[time | None] = mapped_column(Time)
    workday_start: Mapped[time | None] = mapped_column(Time)
    workday_end: Mapped[time | None] = mapped_column(Time)
    quiet_start: Mapped[time | None] = mapped_column(Time)
    quiet_end: Mapped[time | None] = mapped_column(Time)
    dm_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    fallback_channel_id: Mapped[str | None] = mapped_column(String(24))
    dashboard_channel_id: Mapped[str | None] = mapped_column(String(24))
    dashboard_message_id: Mapped[str | None] = mapped_column(String(24))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )


class AuditLog(Base):
    """Schema skeleton required by DATABASE.md; no audit UI/workflows in P1."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("actor IN ('owner', 'agent', 'system')", name="actor"),
        CheckConstraint("result IN ('success', 'denied', 'error')", name="result"),
        Index("ix_audit_logs_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str | None] = mapped_column(String(24), ForeignKey("users.discord_user_id"))
    actor: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    safe_metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class CoreRecord:
    """Application-generated IDs/timestamps; SQL checks also protect direct writes."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("users.discord_user_id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )


def validate_text(value: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Tên phải có nội dung và dài tối đa {maximum} ký tự.")
    return value


class Project(CoreRecord, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_projects_id_owner"),
        CheckConstraint("length(name) <= 200 AND length(trim(name)) > 0", name="name_length"),
        CheckConstraint("status IN ('active', 'paused', 'completed', 'archived')", name="status"),
        Index("ix_projects_owner_status", "owner_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default=ProjectStatus.ACTIVE, server_default="active", nullable=False
    )
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Only project_id is synchronized: assigning a relationship must never rewrite owner_id.
    tasks: Mapped[list[Task]] = relationship(
        back_populates="project",
        primaryjoin=lambda: and_(Project.id == Task.project_id, Project.owner_id == Task.owner_id),
        foreign_keys=lambda: [Task.project_id],
        lazy="raise",
        passive_deletes="all",
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        return validate_text(value, 200)

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        return ProjectStatus(value).value


class Task(CoreRecord, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_tasks_id_owner"),
        ForeignKeyConstraint(
            ["project_id", "owner_id"],
            ["projects.id", "projects.owner_id"],
            name="fk_tasks_project_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(title) <= 250 AND length(trim(title)) > 0", name="title_length"),
        CheckConstraint("status IN ('todo', 'doing', 'done', 'cancelled')", name="status"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="priority"),
        CheckConstraint(
            "estimated_minutes IS NULL OR "
            "(estimated_minutes > 0 AND estimated_minutes = CAST(estimated_minutes AS INTEGER))",
            name="estimated_minutes",
        ),
        CheckConstraint("version > 0 AND version = CAST(version AS INTEGER)", name="version"),
        Index("ix_tasks_owner_status_due", "owner_id", "status", "due_at"),
        Index("ix_tasks_project_status", "project_id", "status"),
    )

    project_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default=TaskStatus.TODO, server_default="todo", nullable=False
    )
    priority: Mapped[str] = mapped_column(
        String(20), default=TaskPriority.MEDIUM, server_default="medium", nullable=False
    )
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    __mapper_args__ = {"version_id_col": version}

    project: Mapped[Project | None] = relationship(
        back_populates="tasks",
        primaryjoin=lambda: and_(Project.id == Task.project_id, Project.owner_id == Task.owner_id),
        foreign_keys=lambda: [Task.project_id],
        lazy="raise",
    )
    calendar_events: Mapped[list[CalendarEvent]] = relationship(
        back_populates="task",
        primaryjoin=lambda: and_(
            Task.id == CalendarEvent.task_id, Task.owner_id == CalendarEvent.owner_id
        ),
        foreign_keys=lambda: [CalendarEvent.task_id],
        lazy="raise",
        passive_deletes="all",
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="task",
        primaryjoin=lambda: and_(Task.id == Reminder.task_id, Task.owner_id == Reminder.owner_id),
        foreign_keys=lambda: [Reminder.task_id],
        lazy="raise",
        passive_deletes="all",
    )

    @validates("title")
    def validate_title(self, key: str, value: str) -> str:
        return validate_text(value, 250)

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        return TaskStatus(value).value

    @validates("priority")
    def validate_priority(self, key: str, value: str) -> str:
        return TaskPriority(value).value

    @validates("estimated_minutes", "version")
    def validate_positive_integer(self, key: str, value: int | None) -> int | None:
        if value is None and key == "estimated_minutes":
            return None
        if type(value) is not int or value <= 0:
            raise ValueError(f"{key} phải là số nguyên dương.")
        return value


class CalendarEvent(CoreRecord, Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        Index("ux_calendar_events_id_owner", "id", "owner_id", unique=True),
        ForeignKeyConstraint(
            ["task_id", "owner_id"],
            ["tasks.id", "tasks.owner_id"],
            name="fk_calendar_events_task_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(title) <= 250 AND length(trim(title)) > 0", name="title_length"),
        CheckConstraint("ends_at > starts_at", name="time_range"),
        CheckConstraint("status IN ('proposed', 'confirmed', 'cancelled')", name="status"),
        CheckConstraint("origin IN ('manual', 'agent', 'integration')", name="origin"),
        CheckConstraint("version > 0 AND version = CAST(version AS INTEGER)", name="version"),
        Index("ix_calendar_events_owner_range", "owner_id", "starts_at", "ends_at"),
        Index("ix_calendar_events_task_owner", "task_id", "owner_id"),
    )

    task_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=EventStatus.PROPOSED, server_default="proposed", nullable=False
    )
    is_fixed: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="is_fixed"),
        default=False,
        server_default="0",
        nullable=False,
    )
    origin: Mapped[str] = mapped_column(
        String(20), default=EventOrigin.MANUAL, server_default="manual", nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    __mapper_args__ = {"version_id_col": version}

    task: Mapped[Task | None] = relationship(
        back_populates="calendar_events",
        primaryjoin=lambda: and_(
            Task.id == CalendarEvent.task_id, Task.owner_id == CalendarEvent.owner_id
        ),
        foreign_keys=lambda: [CalendarEvent.task_id],
        lazy="raise",
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="event",
        primaryjoin=lambda: and_(
            CalendarEvent.id == Reminder.event_id, CalendarEvent.owner_id == Reminder.owner_id
        ),
        foreign_keys=lambda: [Reminder.event_id],
        lazy="raise",
        passive_deletes="all",
    )

    @validates("title")
    def validate_title(self, key: str, value: str) -> str:
        return validate_text(value, 250)

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        return EventStatus(value).value

    @validates("origin")
    def validate_origin(self, key: str, value: str) -> str:
        return EventOrigin(value).value

    @validates("version")
    def validate_version(self, key: str, value: int) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError("version phải là số nguyên dương.")
        return value

    @validates("is_fixed")
    def validate_is_fixed(self, key: str, value: bool) -> bool:
        if type(value) is not bool:
            raise ValueError("is_fixed phải là boolean.")
        return value


class Reminder(CoreRecord, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "owner_id"],
            ["tasks.id", "tasks.owner_id"],
            name="fk_reminders_task_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["event_id", "owner_id"],
            ["calendar_events.id", "calendar_events.owner_id"],
            name="fk_reminders_event_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(title) <= 250 AND length(trim(title)) > 0", name="title_length"),
        CheckConstraint("recurrence_type IN ('none', 'daily', 'weekly')", name="recurrence_type"),
        CheckConstraint(
            "(recurrence_type = 'none' AND recurrence_config_json IS NULL) OR "
            "(recurrence_type IN ('daily', 'weekly') AND recurrence_config_json IS NOT NULL)",
            name="recurrence_config",
        ),
        CheckConstraint("delivery_target IN ('dm', 'channel')", name="delivery_target"),
        CheckConstraint(
            "(delivery_target = 'dm' AND channel_id IS NULL) OR "
            "(delivery_target = 'channel' AND channel_id IS NOT NULL)",
            name="delivery_channel",
        ),
        CheckConstraint("status IN ('active', 'paused', 'done', 'cancelled')", name="status"),
        Index("ix_reminders_status_fire", "status", "next_fire_at"),
        Index("ix_reminders_owner_status", "owner_id", "status"),
        Index("ix_reminders_task_owner", "task_id", "owner_id"),
        Index("ix_reminders_event_owner", "event_id", "owner_id"),
    )

    task_id: Mapped[str | None] = mapped_column(String(36))
    event_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    next_fire_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    recurrence_type: Mapped[str] = mapped_column(
        String(20), default=RecurrenceType.NONE, server_default="none", nullable=False
    )
    recurrence_config_json: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    delivery_target: Mapped[str] = mapped_column(
        String(20), default=DeliveryTarget.DM, server_default="dm", nullable=False
    )
    channel_id: Mapped[str | None] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(
        String(20), default=ReminderStatus.ACTIVE, server_default="active", nullable=False
    )
    task: Mapped[Task | None] = relationship(
        back_populates="reminders",
        primaryjoin=lambda: and_(Task.id == Reminder.task_id, Task.owner_id == Reminder.owner_id),
        foreign_keys=lambda: [Reminder.task_id],
        lazy="raise",
    )
    event: Mapped[CalendarEvent | None] = relationship(
        back_populates="reminders",
        primaryjoin=lambda: and_(
            CalendarEvent.id == Reminder.event_id, CalendarEvent.owner_id == Reminder.owner_id
        ),
        foreign_keys=lambda: [Reminder.event_id],
        lazy="raise",
    )
    deliveries: Mapped[list[ReminderDelivery]] = relationship(
        back_populates="reminder",
        foreign_keys=lambda: [ReminderDelivery.reminder_id],
        lazy="raise",
        passive_deletes="all",
    )

    @validates("title")
    def validate_title(self, key: str, value: str) -> str:
        return validate_text(value, 250)

    @validates("recurrence_type", "delivery_target", "status")
    def validate_enum(self, key: str, value: str) -> str:
        enum = {
            "recurrence_type": RecurrenceType,
            "delivery_target": DeliveryTarget,
            "status": ReminderStatus,
        }[key]
        return enum(value).value

    @validates("recurrence_config_json")
    def validate_config(self, key: str, value: dict | None) -> dict | None:
        return RecurrenceRule.from_config(value).to_config() if value is not None else None

    @validates("channel_id")
    def validate_channel(self, key: str, value: str | None) -> str | None:
        return discord_id(value) if value is not None else None


@event.listens_for(Reminder, "before_insert")
@event.listens_for(Reminder, "before_update")
def validate_reminder_record(mapper, connection, target: Reminder) -> None:
    # Validate the complete record after all attributes/relationships are set.
    # Future-time checks belong to the create service, not loading/retrying old rows.
    ReminderData(
        title=target.title,
        next_fire_at=target.next_fire_at,
        task_id=target.task_id,
        event_id=target.event_id,
        recurrence_type=target.recurrence_type or RecurrenceType.NONE,
        recurrence=(
            RecurrenceRule.from_config(target.recurrence_config_json)
            if target.recurrence_config_json is not None
            else None
        ),
        delivery_target=target.delivery_target or DeliveryTarget.DM,
        channel_id=target.channel_id,
        status=target.status or ReminderStatus.ACTIVE,
    )


class ReminderDelivery(Base):
    __tablename__ = "reminder_deliveries"
    __table_args__ = (
        UniqueConstraint("reminder_id", "scheduled_fire_at", name="uq_reminder_deliveries_fire"),
        UniqueConstraint("id", "reminder_id", name="uq_reminder_deliveries_id_reminder"),
        UniqueConstraint("parent_delivery_id", name="uq_reminder_deliveries_parent"),
        ForeignKeyConstraint(
            ["parent_delivery_id", "reminder_id"],
            ["reminder_deliveries.id", "reminder_deliveries.reminder_id"],
            name="fk_reminder_deliveries_parent_reminder",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('pending', 'claimed', 'sent', 'failed')", name="status"),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count = CAST(attempt_count AS INTEGER)",
            name="attempt_count",
        ),
        CheckConstraint("delivery_kind IN ('scheduled', 'snooze')", name="delivery_kind"),
        CheckConstraint(
            "(delivery_kind = 'scheduled' AND parent_delivery_id IS NULL) OR "
            "(delivery_kind = 'snooze' AND parent_delivery_id IS NOT NULL)",
            name="snooze_parent",
        ),
        CheckConstraint("parent_delivery_id IS NULL OR parent_delivery_id != id", name="not_self"),
        CheckConstraint(
            "last_error_code IS NULL OR last_error_code IN "
            "('forbidden', 'http_error', 'network_error', 'timeout', 'unknown_error')",
            name="safe_error_code",
        ),
        Index("ix_reminder_deliveries_status_fire", "status", "scheduled_fire_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    reminder_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reminders.id", ondelete="RESTRICT"), nullable=False
    )
    scheduled_fire_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=DeliveryStatus.PENDING, server_default="pending", nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    discord_message_id: Mapped[str | None] = mapped_column(String(24))
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    claim_token: Mapped[str | None] = mapped_column(String(36))
    finished_reason: Mapped[str | None] = mapped_column(String(20))
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    delivery_kind: Mapped[str] = mapped_column(
        String(20), default=DeliveryKind.SCHEDULED, server_default="scheduled", nullable=False
    )
    parent_delivery_id: Mapped[str | None] = mapped_column(String(36))
    reminder: Mapped[Reminder] = relationship(
        back_populates="deliveries", foreign_keys=[reminder_id], lazy="raise"
    )

    @validates("status", "delivery_kind", "last_error_code")
    def validate_enum(self, key: str, value: str | None) -> str | None:
        if key == "last_error_code" and value is None:
            return None
        enum = {
            "status": DeliveryStatus,
            "delivery_kind": DeliveryKind,
            "last_error_code": DeliveryErrorCode,
        }[key]
        return enum(value).value

    @validates("attempt_count")
    def validate_attempt_count(self, key: str, value: int) -> int:
        if type(value) is not int or value < 0:
            raise ValueError("attempt_count phải là số nguyên không âm.")
        return value

    @validates("discord_message_id")
    def validate_message_id(self, key: str, value: str | None) -> str | None:
        return discord_id(value) if value is not None else None
