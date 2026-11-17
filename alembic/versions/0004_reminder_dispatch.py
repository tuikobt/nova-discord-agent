"""Durable retry/claim/ack metadata; only add nullable columns to P4 deliveries."""

import sqlalchemy as sa
from alembic import context, op

revision = "0004_reminder_dispatch"
down_revision = "0003_reminders"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in (
        ("retry_at", sa.DateTime(timezone=True)),
        ("claim_token", sa.String(36)),
        ("finished_reason", sa.String(20)),
        ("acknowledged_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("reminder_deliveries", sa.Column(name, kind, nullable=True))


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("Downgrade cần kiểm tra lịch sử gửi trước khi bỏ metadata.")
    if op.get_bind().scalar(sa.text("SELECT 1 FROM reminder_deliveries LIMIT 1")):
        raise RuntimeError("Không downgrade khi có lịch sử delivery; hãy backup/restore.")
    for name in ("acknowledged_at", "finished_reason", "claim_token", "retry_at"):
        op.drop_column("reminder_deliveries", name)
