
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.memory import Memory, utc_now
from app.models.memory_enrichment import MemoryEnrichment
from app.schemas.memory_enrichment import MemoryEnrichmentV1


class MemoryEnrichmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_if_memory_unchanged(
        self,
        memory_id: str,
        source_content_hash: str,
        enrichment: MemoryEnrichmentV1,
        schema_version: str,
        prompt_version: str,
        model: str,
    ) -> bool:
        """Persist enrichment only if the source memory still matches."""

        try:
            memory_statement = (
                select(Memory)
                .where(Memory.id == memory_id)
                .with_for_update()
            )
            memory = self.session.scalar(memory_statement)

            if memory is None:
                self.session.rollback()
                return False

            current_hash = hashlib.sha256(
                memory.content.encode("utf-8")
            ).hexdigest()

            if current_hash != source_content_hash:
                self.session.rollback()
                return False

            existing_statement = select(MemoryEnrichment).where(
                MemoryEnrichment.memory_id == memory_id
            )
            existing = self.session.scalar(existing_statement)

            values = {
                "summary": enrichment.summary,
                "category": (
                    enrichment.category.value
                    if enrichment.category is not None
                    else None
                ),
                "memory_type": (
                    enrichment.memory_type.value
                    if enrichment.memory_type is not None
                    else None
                ),
                "tags": list(enrichment.tags),
                "entities": [
                    entity.model_dump(mode="json")
                    for entity in enrichment.entities
                ],
                "importance": enrichment.importance,
                "schema_version": schema_version,
                "prompt_version": prompt_version,
                "model": model,
                "source_content_hash": source_content_hash,
            }

            if existing is None:
                record = MemoryEnrichment(
                    memory_id=memory_id,
                    **values,
                )
                self.session.add(record)
            else:
                for field, value in values.items():
                    setattr(existing, field, value)

                existing.updated_at = utc_now()

            self.session.commit()
            return True

        except Exception:
            self.session.rollback()
            raise
