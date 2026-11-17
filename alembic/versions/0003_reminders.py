"""Phase 4A reminder schema; preserve every Phase 1-3 table and row."""

import sqlalchemy as sa
from alembic import context, op

revision = "0003_reminders"
down_revision = "0002_core_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # An index supplies the composite FK target without rebuilding the P3 table.
    op.create_index(
        "ux_calendar_events_id_owner", "calendar_events", ["id", "owner_id"], unique=True
    )
    op.create_table(
        "reminders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("event_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recurrence_type", sa.String(20), server_default="none", nullable=False),
        sa.Column("recurrence_config_json", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("delivery_target", sa.String(20), server_default="dm", nullable=False),
        sa.Column("channel_id", sa.String(24), nullable=True),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.discord_user_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["task_id", "owner_id"],
            ["tasks.id", "tasks.owner_id"],
            name="fk_reminders_task_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "owner_id"],
            ["calendar_events.id", "calendar_events.owner_id"],
            name="fk_reminders_event_owner",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("length(title) <= 250 AND length(trim(title)) > 0", name="title_length"),
        sa.CheckConstraint(
            "recurrence_type IN ('none', 'daily', 'weekly')", name="recurrence_type"
        ),
        sa.CheckConstraint(
            "(recurrence_type = 'none' AND recurrence_config_json IS NULL) OR "
            "(recurrence_type IN ('daily', 'weekly') AND recurrence_config_json IS NOT NULL)",
            name="recurrence_config",
        ),
        sa.CheckConstraint("delivery_target IN ('dm', 'channel')", name="delivery_target"),
        sa.CheckConstraint(
            "(delivery_target = 'dm' AND channel_id IS NULL) OR "
            "(delivery_target = 'channel' AND channel_id IS NOT NULL)",
            name="delivery_channel",
        ),
        sa.CheckConstraint("status IN ('active', 'paused', 'done', 'cancelled')", name="status"),
    )
    op.create_index("ix_reminders_status_fire", "reminders", ["status", "next_fire_at"])
    op.create_index("ix_reminders_owner_status", "reminders", ["owner_id", "status"])
    op.create_index("ix_reminders_task_owner", "reminders", ["task_id", "owner_id"])
    op.create_index("ix_reminders_event_owner", "reminders", ["event_id", "owner_id"])
    op.create_table(
        "reminder_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("reminder_id", sa.String(36), nullable=False),
        sa.Column("scheduled_fire_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("discord_message_id", sa.String(24), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_kind", sa.String(20), server_default="scheduled", nullable=False),
        sa.Column("parent_delivery_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(["reminder_id"], ["reminders.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("reminder_id", "scheduled_fire_at", name="uq_reminder_deliveries_fire"),
        sa.UniqueConstraint("id", "reminder_id", name="uq_reminder_deliveries_id_reminder"),
        sa.UniqueConstraint("parent_delivery_id", name="uq_reminder_deliveries_parent"),
        sa.ForeignKeyConstraint(
            ["parent_delivery_id", "reminder_id"],
            ["reminder_deliveries.id", "reminder_deliveries.reminder_id"],
            name="fk_reminder_deliveries_parent_reminder",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('pending', 'claimed', 'sent', 'failed')", name="status"),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count = CAST(attempt_count AS INTEGER)",
            name="attempt_count",
        ),
        sa.CheckConstraint("delivery_kind IN ('scheduled', 'snooze')", name="delivery_kind"),
        sa.CheckConstraint(
            "(delivery_kind = 'scheduled' AND parent_delivery_id IS NULL) OR "
            "(delivery_kind = 'snooze' AND parent_delivery_id IS NOT NULL)",
            name="snooze_parent",
        ),
        sa.CheckConstraint(
            "parent_delivery_id IS NULL OR parent_delivery_id != id", name="not_self"
        ),
        sa.CheckConstraint(
            "last_error_code IS NULL OR last_error_code IN "
            "('forbidden', 'http_error', 'network_error', 'timeout', 'unknown_error')",
            name="safe_error_code",
        ),
    )
    op.create_index(
        "ix_reminder_deliveries_status_fire", "reminder_deliveries", ["status", "scheduled_fire_at"]
    )


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Downgrade cần kết nối DB để kiểm tra dữ liệu P4 trước khi xóa schema.")
    connection = op.get_bind()
    for table in ("reminder_deliveries", "reminders"):
        if connection.scalar(sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1)):
            raise RuntimeError("Không downgrade khi bảng P4 có dữ liệu; hãy sao lưu và restore.")
    op.drop_table("reminder_deliveries")
    op.drop_table("reminders")
    op.drop_index("ux_calendar_events_id_owner", table_name="calendar_events")
