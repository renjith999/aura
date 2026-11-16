
import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.models.memory import Memory, utc_now
from app.models.memory_enrichment import MemoryEnrichment
from app.schemas.memory_enrichment import MemoryEnrichmentV1

PENDING = "pending"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"
MAX_ATTEMPTS = 3
LEASE_SECONDS = 90
RETRY_DELAYS_SECONDS = (5, 30)


@dataclass(frozen=True)
class EnrichmentClaim:
    memory_id: str
    source_content_hash: str
    attempt_count: int


class MemoryEnrichmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_memory(self, memory_id: str) -> MemoryEnrichment | None:
        return self.session.get(MemoryEnrichment, memory_id)

    def create_or_reset_pending(
        self,
        memory_id: str,
        content: str,
        schema_version: str,
        prompt_version: str,
        model: str,
    ) -> MemoryEnrichment:
        record = self.session.get(MemoryEnrichment, memory_id)
        values = {
            "summary": None,
            "category": None,
            "memory_type": None,
            "tags": [],
            "entities": [],
            "importance": None,
            "schema_version": schema_version,
            "prompt_version": prompt_version,
            "model": model,
            "source_content_hash": hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest(),
            "status": PENDING,
            "attempt_count": 0,
            "last_error": None,
            "next_retry_at": None,
            "lease_expires_at": None,
            "completed_at": None,
        }

        if record is None:
            record = MemoryEnrichment(memory_id=memory_id, **values)
            self.session.add(record)
        else:
            for field, value in values.items():
                setattr(record, field, value)
        return record

    def claim(
        self,
        memory_id: str | None = None,
        now: datetime | None = None,
    ) -> EnrichmentClaim | None:
        now = now or datetime.now(UTC)
        eligible = or_(
            and_(
                MemoryEnrichment.status == PENDING,
                MemoryEnrichment.attempt_count < MAX_ATTEMPTS,
            ),
            and_(
                MemoryEnrichment.status == FAILED,
                MemoryEnrichment.next_retry_at.is_not(None),
                MemoryEnrichment.next_retry_at <= now,
                MemoryEnrichment.attempt_count < MAX_ATTEMPTS,
            ),
            and_(
                MemoryEnrichment.status == PROCESSING,
                MemoryEnrichment.lease_expires_at.is_not(None),
                MemoryEnrichment.lease_expires_at <= now,
                MemoryEnrichment.attempt_count < MAX_ATTEMPTS,
            ),
        )
        statement = select(MemoryEnrichment).where(eligible)
        if memory_id is not None:
            statement = statement.where(MemoryEnrichment.memory_id == memory_id)
        statement = (
            statement.order_by(MemoryEnrichment.created_at, MemoryEnrichment.memory_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        candidate = self.session.scalar(statement)
        if candidate is None:
            self.session.rollback()
            return None

        claim_statement = (
            update(MemoryEnrichment)
            .where(
                MemoryEnrichment.memory_id == candidate.memory_id,
                MemoryEnrichment.status == candidate.status,
                MemoryEnrichment.attempt_count == candidate.attempt_count,
                eligible,
            )
            .values(
                status=PROCESSING,
                attempt_count=MemoryEnrichment.attempt_count + 1,
                lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                last_error=None,
                next_retry_at=None,
            )
            .returning(
                MemoryEnrichment.memory_id,
                MemoryEnrichment.source_content_hash,
                MemoryEnrichment.attempt_count,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = self.session.execute(claim_statement).one_or_none()

        if claimed is None:
            self.session.rollback()
            return None

        self.session.commit()
        self.session.expire_all()
        return EnrichmentClaim(
            memory_id=claimed.memory_id,
            source_content_hash=claimed.source_content_hash,
            attempt_count=claimed.attempt_count,
        )

    def complete(
        self,
        claim: EnrichmentClaim,
        enrichment: MemoryEnrichmentV1,
        schema_version: str,
        prompt_version: str,
        model: str,
        now: datetime | None = None,
    ) -> bool:
        now = now or datetime.now(UTC)
        try:
            memory = self.session.scalar(
                select(Memory)
                .where(Memory.id == claim.memory_id)
                .with_for_update()
            )
            record = self.session.get(MemoryEnrichment, claim.memory_id)
            if (
                memory is None
                or record is None
                or record.status != PROCESSING
                or record.attempt_count != claim.attempt_count
                or record.source_content_hash != claim.source_content_hash
                or hashlib.sha256(memory.content.encode("utf-8")).hexdigest()
                != claim.source_content_hash
            ):
                self.session.rollback()
                return False

            record.summary = enrichment.summary
            record.category = (
                enrichment.category.value if enrichment.category is not None else None
            )
            record.memory_type = (
                enrichment.memory_type.value
                if enrichment.memory_type is not None
                else None
            )
            record.tags = list(enrichment.tags)
            record.entities = [
                entity.model_dump(mode="json") for entity in enrichment.entities
            ]
            record.importance = enrichment.importance
            record.schema_version = schema_version
            record.prompt_version = prompt_version
            record.model = model
            record.status = COMPLETED
            record.completed_at = now
            record.last_error = None
            record.next_retry_at = None
            record.lease_expires_at = None
            record.updated_at = now
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            raise

    def fail(
        self,
        claim: EnrichmentClaim,
        error_code: str,
        retryable: bool,
        now: datetime | None = None,
    ) -> bool:
        now = now or datetime.now(UTC)
        try:
            record = self.session.get(MemoryEnrichment, claim.memory_id)
            if (
                record is None
                or record.status != PROCESSING
                or record.attempt_count != claim.attempt_count
                or record.source_content_hash != claim.source_content_hash
            ):
                self.session.rollback()
                return False

            delay = None
            if retryable and claim.attempt_count < MAX_ATTEMPTS:
                base_delay = RETRY_DELAYS_SECONDS[claim.attempt_count - 1]
                delay = base_delay * random.uniform(0.8, 1.2)

            record.status = FAILED
            record.last_error = error_code[:100]
            record.next_retry_at = (
                now + timedelta(seconds=delay) if delay is not None else None
            )
            record.lease_expires_at = None
            record.completed_at = None
            record.updated_at = now
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            raise

    def fail_expired_final_attempts(
        self,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(UTC)
        result = self.session.execute(
            update(MemoryEnrichment)
            .where(
                MemoryEnrichment.status == PROCESSING,
                MemoryEnrichment.attempt_count >= MAX_ATTEMPTS,
                MemoryEnrichment.lease_expires_at <= now,
            )
            .values(
                status=FAILED,
                last_error="worker_lease_expired",
                next_retry_at=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        self.session.commit()
        return result.rowcount or 0

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
                "status": COMPLETED,
                "attempt_count": 1,
                "completed_at": utc_now(),
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
                existing.status = COMPLETED
                existing.attempt_count = max(existing.attempt_count, 1)
                existing.completed_at = utc_now()
                existing.last_error = None
                existing.next_retry_at = None
                existing.lease_expires_at = None

            self.session.commit()
            return True

        except Exception:
            self.session.rollback()
            raise
