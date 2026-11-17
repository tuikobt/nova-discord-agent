"""Add durable AI proposals and usage, without altering P1-P4 tables."""

import sqlalchemy as sa
from alembic import context, op

revision = "0005_agent"
down_revision = "0004_reminder_dispatch"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(24), sa.ForeignKey("users.discord_user_id"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("action_type", sa.String(80), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("channel_id", sa.String(24)),
        sa.Column("message_id", sa.String(24)),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_pending_owner_key"),
        sa.CheckConstraint(
            "status IN ('pending','rejected','expired','executed')",
            name=op.f("ck_pending_actions_status"),
        ),
    )
    op.create_index("ix_pending_owner_expiry", "pending_actions", ["owner_id", "expires_at"])
    op.create_table(
        "agent_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(24), sa.ForeignKey("users.discord_user_id"), nullable=False
        ),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("charged_tokens", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("settled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "charged_tokens >= 0 AND input_tokens >= 0 AND output_tokens >= 0",
            name=op.f("ck_agent_usage_tokens"),
        ),
    )
    op.create_index("ix_agent_usage_owner_created", "agent_usage", ["owner_id", "created_at"])


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("Offline downgrade cannot verify AI history.")
    for table in ("pending_actions", "agent_usage"):
        if op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Refusing to discard AI history; disable AI or export first.")
    op.drop_table("agent_usage")
    op.drop_table("pending_actions")
