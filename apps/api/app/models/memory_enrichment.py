
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryEnrichment(Base):
    __tablename__ = "memory_enrichments"

    memory_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("memories.id", ondelete="CASCADE"),
        primary_key=True,
    )

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    memory_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    tags: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )

    entities: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )

    importance: Mapped[int | None] = mapped_column(Integer, nullable=True)

    schema_version: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    prompt_version: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    model: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    source_content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
