"""Create per-user chat usage windows."""

import sqlalchemy as sa
from alembic import op

revision = "0003_chat_usage_windows"
down_revision = "0002_create_users_and_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_usage_windows",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("chat_usage_windows")
