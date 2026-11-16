"""add enrichment status and retry tracking

Revision ID: a58f3b8c1d20
Revises: eddc57be03de
Create Date: 2026-11-15 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a58f3b8c1d20"
down_revision: str | Sequence[str] | None = "eddc57be03de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_enrichments",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="completed",
        ),
    )
    op.add_column(
        "memory_enrichments",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "memory_enrichments",
        sa.Column("last_error", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "memory_enrichments",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memory_enrichments",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memory_enrichments",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_memory_enrichments_status",
        "memory_enrichments",
        "status IN ('pending', 'processing', 'completed', 'failed')",
    )
    op.create_check_constraint(
        "ck_memory_enrichments_attempt_count",
        "memory_enrichments",
        "attempt_count >= 0",
    )
    op.execute(
        "UPDATE memory_enrichments SET completed_at = created_at "
        "WHERE status = 'completed' AND completed_at IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_memory_enrichments_attempt_count",
        "memory_enrichments",
        type_="check",
    )
    op.drop_constraint(
        "ck_memory_enrichments_status",
        "memory_enrichments",
        type_="check",
    )
    op.drop_column("memory_enrichments", "completed_at")
    op.drop_column("memory_enrichments", "lease_expires_at")
    op.drop_column("memory_enrichments", "next_retry_at")
    op.drop_column("memory_enrichments", "last_error")
    op.drop_column("memory_enrichments", "attempt_count")
    op.drop_column("memory_enrichments", "status")
