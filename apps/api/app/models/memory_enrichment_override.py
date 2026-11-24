from sqlalchemy import JSON, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MemoryEnrichmentOverride(Base):
    """User-authored values that take precedence over AI enrichment."""

    __tablename__ = "memory_enrichment_overrides"

    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    overrides: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
