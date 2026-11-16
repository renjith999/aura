"""Store user-authored memory enrichment overrides.

Revision ID: b59a14d6e320
Revises: a58f3b8c1d20, 0003_chat_usage_windows
Create Date: 2026-11-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b59a14d6e320"
down_revision: str | Sequence[str] | None = (
    "a58f3b8c1d20",
    "0003_chat_usage_windows",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_enrichment_overrides",
        sa.Column("memory_id", sa.String(length=36), nullable=False),
        sa.Column(
            "overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("memory_id"),
    )


def downgrade() -> None:
    op.drop_table("memory_enrichment_overrides")
