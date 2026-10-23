"""Phase 1 users, settings, and audit schema skeleton."""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("discord_user_id", sa.String(24), primary_key=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_settings",
        sa.Column("owner_id", sa.String(24), primary_key=True),
        sa.Column("morning_briefing_time", sa.Time(), nullable=True),
        sa.Column("daily_review_time", sa.Time(), nullable=True),
        sa.Column("workday_start", sa.Time(), nullable=True),
        sa.Column("workday_end", sa.Time(), nullable=True),
        sa.Column("quiet_start", sa.Time(), nullable=True),
        sa.Column("quiet_end", sa.Time(), nullable=True),
        sa.Column("dm_notifications_enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("fallback_channel_id", sa.String(24), nullable=True),
        sa.Column("dashboard_channel_id", sa.String(24), nullable=True),
        sa.Column("dashboard_message_id", sa.String(24), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.discord_user_id"], ondelete="CASCADE"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(24), nullable=True),
        sa.Column("actor", sa.String(30), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=True),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("safe_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.discord_user_id"]),
        sa.CheckConstraint("actor IN ('owner', 'agent', 'system')", name="actor"),
        sa.CheckConstraint("result IN ('success', 'denied', 'error')", name="result"),
    )
    op.create_index("ix_audit_logs_owner_created", "audit_logs", ["owner_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_owner_created", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("user_settings")
    op.drop_table("users")
