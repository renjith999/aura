from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryEnrichmentAttempt(Base):
    """Auditable provider-call attempt; never stores memory content."""

    __tablename__ = "memory_enrichment_attempts"
    __table_args__ = (
        UniqueConstraint(
            "generation_id",
            "attempt_number",
            name="uq_memory_enrichment_attempt_generation_number",
        ),
        CheckConstraint(
            "attempt_number > 0",
            name="ck_memory_enrichment_attempt_number",
        ),
        CheckConstraint(
            "outcome IN ('started', 'completed', 'refused', 'incomplete', "
            "'validation_error', 'provider_error', 'transport_error', "
            "'application_error', 'not_sent', 'unknown')",
            name="ck_memory_enrichment_attempt_outcome",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_memory_enrichment_attempt_input_tokens",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_memory_enrichment_attempt_output_tokens",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_memory_enrichment_attempt_total_tokens",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    # Null this reference when a memory is deleted but retain aggregate cost data.
    memory_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("memories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    generation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_model: Mapped[str] = mapped_column(String(100), nullable=False)
    response_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(30), nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(
        String(30), nullable=False, default="started", server_default=text("'started'")
    )
    provider_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    response_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_write_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 12), nullable=True
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default=text("'USD'")
    )
    pricing_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_rate_per_million: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 12), nullable=True
    )
    output_rate_per_million: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 12), nullable=True
    )
    cached_input_rate_per_million: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 12), nullable=True
    )
    cache_write_input_rate_per_million: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 12), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    response_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
