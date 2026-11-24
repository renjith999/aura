"""Record token usage and estimated cost for each enrichment attempt.

Revision ID: c6b7e24a901d
Revises: b59a14d6e320
Create Date: 2026-11-17 00:00:00.000000
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "c6b7e24a901d"
down_revision: str | Sequence[str] | None = "b59a14d6e320"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_enrichments",
        sa.Column("generation_id", sa.String(length=36), nullable=True),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT memory_id FROM memory_enrichments")).all()
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE memory_enrichments SET generation_id = :generation_id "
                "WHERE memory_id = :memory_id"
            ),
            {"generation_id": str(uuid4()), "memory_id": row.memory_id},
        )
    with op.batch_alter_table("memory_enrichments") as batch_op:
        batch_op.alter_column("generation_id", nullable=False)

    op.create_table(
        "memory_enrichment_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("memory_id", sa.String(length=36), nullable=True),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("requested_model", sa.String(length=100), nullable=False),
        sa.Column("response_model", sa.String(length=100), nullable=True),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("prompt_version", sa.String(length=30), nullable=False),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "outcome",
            sa.String(length=30),
            server_default="started",
            nullable=False,
        ),
        sa.Column("provider_status", sa.String(length=30), nullable=True),
        sa.Column("response_id", sa.String(length=100), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_write_input_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_estimate", sa.Numeric(24, 12), nullable=True),
        sa.Column(
            "currency", sa.String(length=3), server_default="USD", nullable=False
        ),
        sa.Column("pricing_version", sa.String(length=80), nullable=False),
        sa.Column("input_rate_per_million", sa.Numeric(24, 12), nullable=True),
        sa.Column("output_rate_per_million", sa.Numeric(24, 12), nullable=True),
        sa.Column("cached_input_rate_per_million", sa.Numeric(24, 12), nullable=True),
        sa.Column(
            "cache_write_input_rate_per_million", sa.Numeric(24, 12), nullable=True
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_number > 0", name="ck_memory_enrichment_attempt_number"
        ),
        sa.CheckConstraint(
            "outcome IN ('started', 'completed', 'refused', 'incomplete', "
            "'validation_error', 'provider_error', 'transport_error', "
            "'application_error', 'not_sent', 'unknown')",
            name="ck_memory_enrichment_attempt_outcome",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_memory_enrichment_attempt_input_tokens",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_memory_enrichment_attempt_output_tokens",
        ),
        sa.CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_memory_enrichment_attempt_total_tokens",
        ),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generation_id",
            "attempt_number",
            name="uq_memory_enrichment_attempt_generation_number",
        ),
    )
    op.create_index(
        "ix_memory_enrichment_attempts_memory_id",
        "memory_enrichment_attempts",
        ["memory_id"],
    )
    op.create_index(
        "ix_memory_enrichment_attempts_generation_id",
        "memory_enrichment_attempts",
        ["generation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_memory_enrichment_attempts_generation_id",
        table_name="memory_enrichment_attempts",
    )
    op.drop_index(
        "ix_memory_enrichment_attempts_memory_id",
        table_name="memory_enrichment_attempts",
    )
    op.drop_table("memory_enrichment_attempts")
    op.drop_column("memory_enrichments", "generation_id")
