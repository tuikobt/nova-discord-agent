"""Only Phase 1 tables; no task, calendar, reminder, or AI persistence."""

from datetime import datetime, time
from uuid import uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utc_now


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
