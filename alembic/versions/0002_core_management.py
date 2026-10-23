"""Phase 3A projects, tasks, calendar; preserve all Foundation tables/data."""

import sqlalchemy as sa
from alembic import context, op

revision = "0002_core_management"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def identity_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "projects",
        *identity_columns(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.discord_user_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "owner_id", name="uq_projects_id_owner"),
        sa.CheckConstraint("length(name) <= 200 AND length(trim(name)) > 0", name="name_length"),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'archived')", name="status"
        ),
    )
    op.create_index("ix_projects_owner_status", "projects", ["owner_id", "status"])
    op.create_table(
        "tasks",
        *identity_columns(),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="todo"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.discord_user_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "owner_id"],
            ["projects.id", "projects.owner_id"],
            name="fk_tasks_project_owner",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "owner_id", name="uq_tasks_id_owner"),
        sa.CheckConstraint("length(title) <= 250 AND length(trim(title)) > 0", name="title_length"),
        sa.CheckConstraint("status IN ('todo', 'doing', 'done', 'cancelled')", name="status"),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="priority"),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR "
            "(estimated_minutes > 0 AND estimated_minutes = CAST(estimated_minutes AS INTEGER))",
            name="estimated_minutes",
        ),
        sa.CheckConstraint("version > 0 AND version = CAST(version AS INTEGER)", name="version"),
    )
    op.create_index("ix_tasks_owner_status_due", "tasks", ["owner_id", "status", "due_at"])
    op.create_index("ix_tasks_project_status", "tasks", ["project_id", "status"])
    op.create_table(
        "calendar_events",
        *identity_columns(),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column(
            "is_fixed",
            sa.Boolean(create_constraint=True, name="is_fixed"),
            nullable=False,
            server_default="0",
        ),
        sa.Column("origin", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.discord_user_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["task_id", "owner_id"],
            ["tasks.id", "tasks.owner_id"],
            name="fk_calendar_events_task_owner",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("length(title) <= 250 AND length(trim(title)) > 0", name="title_length"),
        sa.CheckConstraint("ends_at > starts_at", name="time_range"),
        sa.CheckConstraint("status IN ('proposed', 'confirmed', 'cancelled')", name="status"),
        sa.CheckConstraint("origin IN ('manual', 'agent', 'integration')", name="origin"),
        sa.CheckConstraint("version > 0 AND version = CAST(version AS INTEGER)", name="version"),
    )
    op.create_index(
        "ix_calendar_events_owner_range", "calendar_events", ["owner_id", "starts_at", "ends_at"]
    )
    op.create_index("ix_calendar_events_task_owner", "calendar_events", ["task_id", "owner_id"])


def downgrade() -> None:
    # A schema rollback is only safe while these new tables are empty.
    if context.is_offline_mode():
        raise RuntimeError("Downgrade cần kết nối DB để kiểm tra dữ liệu trước khi xóa schema.")
    connection = op.get_bind()
    for table in ("calendar_events", "tasks", "projects"):
        if connection.scalar(sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1)):
            raise RuntimeError("Không downgrade khi bảng P3 có dữ liệu; hãy sao lưu và restore.")
    op.drop_table("calendar_events")
    op.drop_table("tasks")
    op.drop_table("projects")
