"""Foundation and Phase 3A persistence; no services or Discord CRUD workflows."""

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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base, UTCDateTime, utc_now
from app.domain.enums import EventOrigin, EventStatus, ProjectStatus, TaskPriority, TaskStatus


class User(Base):
    __tablename__ = "users"

    discord_user_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), default="vi-VN", nullable=False)
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
