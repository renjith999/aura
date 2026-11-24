import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.memory import Memory, utc_now
from app.models.memory_enrichment import MemoryEnrichment
from app.models.memory_enrichment_attempt import MemoryEnrichmentAttempt
from app.schemas.memory_enrichment import MemoryEnrichmentV1
from app.services.enrichment_cost import CostEstimate
from app.services.memory_enrichment_service import EnrichmentAttemptData

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
    attempt_id: str
    generation_id: str
    source_content_hash: str
    attempt_count: int
    model: str
    schema_version: str
    prompt_version: str


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
            "generation_id": str(uuid4()),
            "summary": None,
            "category": None,
            "memory_type": None,
            "tags": [],
            "entities": [],
            "importance": None,
            "schema_version": schema_version,
            "prompt_version": prompt_version,
            "model": model,
            "source_content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
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
                MemoryEnrichment.generation_id,
                MemoryEnrichment.source_content_hash,
                MemoryEnrichment.attempt_count,
                MemoryEnrichment.model,
                MemoryEnrichment.schema_version,
                MemoryEnrichment.prompt_version,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = self.session.execute(claim_statement).one_or_none()

        if claimed is None:
            self.session.rollback()
            return None

        if candidate.status == PROCESSING:
            prior_attempt = self.session.scalar(
                select(MemoryEnrichmentAttempt).where(
                    MemoryEnrichmentAttempt.generation_id == candidate.generation_id,
                    MemoryEnrichmentAttempt.attempt_number == candidate.attempt_count,
                    MemoryEnrichmentAttempt.outcome == "started",
                )
            )
            if prior_attempt is not None:
                prior_attempt.outcome = "unknown"
                prior_attempt.recorded_at = now

        attempt_id = str(uuid4())
        self.session.add(
            MemoryEnrichmentAttempt(
                id=attempt_id,
                memory_id=claimed.memory_id,
                generation_id=claimed.generation_id,
                attempt_number=claimed.attempt_count,
                requested_model=claimed.model,
                schema_version=claimed.schema_version,
                prompt_version=claimed.prompt_version,
                source_content_hash=claimed.source_content_hash,
                pricing_version=settings.openai_pricing_version,
                started_at=now,
                recorded_at=now,
            )
        )
        self.session.commit()
        self.session.expire_all()
        return EnrichmentClaim(
            memory_id=claimed.memory_id,
            attempt_id=attempt_id,
            generation_id=claimed.generation_id,
            source_content_hash=claimed.source_content_hash,
            attempt_count=claimed.attempt_count,
            model=claimed.model,
            schema_version=claimed.schema_version,
            prompt_version=claimed.prompt_version,
        )

    def complete(
        self,
        claim: EnrichmentClaim,
        enrichment: MemoryEnrichmentV1,
        schema_version: str,
        prompt_version: str,
        model: str,
        now: datetime | None = None,
        attempt_data: EnrichmentAttemptData | None = None,
        cost_estimate: CostEstimate | None = None,
    ) -> bool:
        now = now or datetime.now(UTC)
        try:
            self._finish_attempt(
                claim,
                outcome="completed",
                attempt_data=attempt_data,
                cost_estimate=cost_estimate,
                now=now,
            )
            memory = self.session.scalar(
                select(Memory).where(Memory.id == claim.memory_id).with_for_update()
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
                self.session.commit()
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
        attempt_data: EnrichmentAttemptData | None = None,
        outcome: str = "application_error",
        cost_estimate: CostEstimate | None = None,
    ) -> bool:
        now = now or datetime.now(UTC)
        try:
            self._finish_attempt(
                claim,
                outcome=outcome,
                attempt_data=attempt_data,
                cost_estimate=cost_estimate,
                now=now,
            )
            record = self.session.get(MemoryEnrichment, claim.memory_id)
            if (
                record is None
                or record.status != PROCESSING
                or record.attempt_count != claim.attempt_count
                or record.source_content_hash != claim.source_content_hash
            ):
                self.session.commit()
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
        expired = list(
            self.session.execute(
                select(
                    MemoryEnrichment.generation_id,
                    MemoryEnrichment.attempt_count,
                ).where(
                    MemoryEnrichment.status == PROCESSING,
                    MemoryEnrichment.attempt_count >= MAX_ATTEMPTS,
                    MemoryEnrichment.lease_expires_at <= now,
                )
            )
        )
        for generation_id, attempt_number in expired:
            attempt = self.session.scalar(
                select(MemoryEnrichmentAttempt).where(
                    MemoryEnrichmentAttempt.generation_id == generation_id,
                    MemoryEnrichmentAttempt.attempt_number == attempt_number,
                    MemoryEnrichmentAttempt.outcome == "started",
                )
            )
            if attempt is not None:
                attempt.outcome = "unknown"
                attempt.recorded_at = now
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

    def _finish_attempt(
        self,
        claim: EnrichmentClaim,
        outcome: str,
        attempt_data: EnrichmentAttemptData | None,
        cost_estimate: CostEstimate | None,
        now: datetime,
    ) -> None:
        attempt = self.session.get(MemoryEnrichmentAttempt, claim.attempt_id)
        if attempt is None:
            raise RuntimeError("Enrichment attempt record is missing.")
        attempt.outcome = outcome
        attempt.recorded_at = now
        if attempt_data is not None:
            attempt.response_model = attempt_data.response_model
            attempt.provider_status = attempt_data.provider_status
            attempt.response_id = attempt_data.response_id
            attempt.request_id = attempt_data.request_id
            attempt.response_received_at = attempt_data.response_received_at
            if attempt_data.usage is not None:
                attempt.input_tokens = attempt_data.usage.input_tokens
                attempt.output_tokens = attempt_data.usage.output_tokens
                attempt.total_tokens = attempt_data.usage.total_tokens
                attempt.cached_input_tokens = attempt_data.usage.cached_input_tokens
                attempt.cache_write_input_tokens = (
                    attempt_data.usage.cache_write_input_tokens
                )
                attempt.reasoning_output_tokens = (
                    attempt_data.usage.reasoning_output_tokens
                )
        if cost_estimate is not None:
            attempt.cost_estimate = cost_estimate.amount
            attempt.currency = cost_estimate.currency
            attempt.pricing_version = cost_estimate.pricing_version
            attempt.input_rate_per_million = cost_estimate.input_per_million
            attempt.output_rate_per_million = cost_estimate.output_per_million
            attempt.cached_input_rate_per_million = (
                cost_estimate.cached_input_per_million
            )
            attempt.cache_write_input_rate_per_million = (
                cost_estimate.cache_write_input_per_million
            )

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
                select(Memory).where(Memory.id == memory_id).with_for_update()
            )
            memory = self.session.scalar(memory_statement)

            if memory is None:
                self.session.rollback()
                return False

            current_hash = hashlib.sha256(memory.content.encode("utf-8")).hexdigest()

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
                    entity.model_dump(mode="json") for entity in enrichment.entities
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
