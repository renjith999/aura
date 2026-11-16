from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.models.memory_enrichment_override import MemoryEnrichmentOverride


class MemoryEnrichmentOverrideRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def patch_for_memory(
        self,
        memory_id: str,
        values: dict[str, object],
        clear_fields: list[str],
    ) -> dict[str, object] | None:
        """Merge a manual patch while serializing edits on the parent memory."""
        try:
            memory = self.session.scalar(
                select(Memory).where(Memory.id == memory_id).with_for_update()
            )
            if memory is None:
                self.session.rollback()
                return None

            record = self.session.scalar(
                select(MemoryEnrichmentOverride)
                .where(MemoryEnrichmentOverride.memory_id == memory_id)
                .with_for_update()
            )
            overrides = dict(record.overrides) if record is not None else {}
            for field in clear_fields:
                overrides.pop(field, None)
            overrides.update(values)

            if not overrides:
                if record is not None:
                    self.session.delete(record)
            elif record is None:
                self.session.add(
                    MemoryEnrichmentOverride(
                        memory_id=memory_id,
                        overrides=overrides,
                    )
                )
            else:
                record.overrides = overrides

            self.session.commit()
            return overrides
        except Exception:
            self.session.rollback()
            raise

    def get_for_memory(self, memory_id: str) -> MemoryEnrichmentOverride | None:
        return self.session.get(MemoryEnrichmentOverride, memory_id)
