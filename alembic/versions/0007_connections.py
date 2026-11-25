"""Owner-approved connection metadata only; no external content or secrets."""

import sqlalchemy as sa
from alembic import context, op

revision = "0007_connections"
down_revision = "0006_personal"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(24), sa.ForeignKey("users.discord_user_id"), nullable=False
        ),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("resources_json", sa.JSON(), nullable=False),
        sa.Column("credential_ref", sa.String(32), nullable=False),
        sa.Column("requested_permissions_json", sa.JSON(), nullable=False),
        sa.Column("granted_permissions_json", sa.JSON()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime()),
        sa.Column("last_error_code", sa.String(32)),
        sa.CheckConstraint(
            "provider IN ('github','notion')", name=op.f("ck_integration_connections_provider")
        ),
        sa.CheckConstraint(
            "status IN ('configured','verified','disconnected')",
            name=op.f("ck_integration_connections_status"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_integration_connections_version")),
        sa.CheckConstraint(
            "length(trim(label)) BETWEEN 1 AND 80", name=op.f("ck_integration_connections_label")
        ),
        sa.CheckConstraint(
            "(provider = 'github' AND credential_ref = 'GITHUB_READ_TOKEN') OR "
            "(provider = 'notion' AND credential_ref = 'NOTION_READ_TOKEN')",
            name=op.f("ck_integration_connections_credential_ref"),
        ),
        sa.UniqueConstraint(
            "owner_id", "provider", "label", name="uq_connection_owner_provider_label"
        ),
    )
    op.create_index("ix_connection_owner_status", "integration_connections", ["owner_id", "status"])


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("Offline downgrade cannot verify connection history.")
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM integration_connections")):
        raise RuntimeError(
            "Refusing to discard connection history, including disconnected entries."
        )
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM pending_actions WHERE action_type IN "
            "('configure_connection','disconnect_connection')"
        )
    ):
        raise RuntimeError("Refusing to orphan connection approval history.")
    op.drop_table("integration_connections")
