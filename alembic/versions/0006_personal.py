"""Personal memory and opt-in automation; additive, preserves P1-P5 records."""

import sqlalchemy as sa
from alembic import context, op

revision = "0006_personal"
down_revision = "0005_agent"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "agent_usage", sa.Column("purpose", sa.String(20), nullable=False, server_default="dm")
    )
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(24), sa.ForeignKey("users.discord_user_id"), nullable=False
        ),
        sa.Column("content", sa.String(1000)),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("source", sa.String(128)),
        sa.Column("confirmed_by_owner", sa.Boolean(), nullable=False),
        sa.Column("use_for_ai", sa.Boolean(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime()),
        sa.CheckConstraint(
            "kind IN ('preference','routine','profile')", name=op.f("ck_memory_entries_kind")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_memory_entries_version")),
    )
    op.create_index(
        "ix_memory_owner_active", "memory_entries", ["owner_id", "is_deleted", "use_for_ai"]
    )
    op.create_table(
        "automation_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(24), sa.ForeignKey("users.discord_user_id"), nullable=False
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "kind", name="uq_automation_policy_owner_kind"),
        sa.CheckConstraint(
            "kind IN ('preferences','morning','daily','weekly')",
            name=op.f("ck_automation_policies_kind"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_automation_policies_version")),
    )
    op.create_table(
        "automation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(24), sa.ForeignKey("users.discord_user_id"), nullable=False
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("period_key", sa.String(10), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("claimed_at", sa.DateTime()),
        sa.Column("retry_at", sa.DateTime()),
        sa.Column("payload_json", sa.JSON()),
        sa.Column("error_code", sa.String(30)),
        sa.Column("discord_message_id", sa.String(24)),
        sa.Column("channel_id", sa.String(24)),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "kind", "period_key", name="uq_automation_run_period"),
        sa.CheckConstraint(
            "kind IN ('morning','daily','weekly')", name=op.f("ck_automation_runs_kind")
        ),
        sa.CheckConstraint(
            "status IN ('pending','claimed','sent','failed','skipped')",
            name=op.f("ck_automation_runs_status"),
        ),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_automation_runs_attempt_count")),
    )
    op.create_index("ix_automation_run_due", "automation_runs", ["status", "scheduled_at"])


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("Offline downgrade cannot verify personal history.")
    for name in ("memory_entries", "automation_policies", "automation_runs"):
        if op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {name}")):
            raise RuntimeError("Refusing to discard personal data; disable automation first.")
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM agent_usage WHERE purpose <> 'dm'")):
        raise RuntimeError("Refusing to discard background usage metadata.")
    op.drop_table("automation_runs")
    op.drop_table("automation_policies")
    op.drop_table("memory_entries")
    op.drop_column("agent_usage", "purpose")
