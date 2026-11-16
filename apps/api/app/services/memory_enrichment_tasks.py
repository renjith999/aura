import asyncio
import hashlib
import logging
from collections.abc import Callable

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.memory import Memory
from app.repositories.memory_enrichment_repository import (
    EnrichmentClaim,
    MemoryEnrichmentRepository,
)
from app.services.memory_enrichment_service import (
    MemoryEnrichmentIncompleteError,
    MemoryEnrichmentProviderError,
    MemoryEnrichmentService,
)

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 1.0


async def process_memory_enrichment(
    memory_id: str | None = None,
    service_factory: Callable[[], MemoryEnrichmentService] | None = None,
) -> bool:
    """Claim and process one pending or retryable enrichment job."""
    try:
        with SessionLocal() as session:
            claim = MemoryEnrichmentRepository(session).claim(memory_id)
    except Exception:
        logger.exception("Could not claim enrichment work for %s.", memory_id)
        return False

    if claim is None:
        return False

    try:
        content = _load_claimed_content(claim)
        if (
            content is None
            or hashlib.sha256(content.encode("utf-8")).hexdigest()
            != claim.source_content_hash
        ):
            _mark_failed(claim, "source_content_changed", retryable=False)
            return True

        service = (service_factory or MemoryEnrichmentService)()
        result = await service.enrich_with_metadata(content)

        with SessionLocal() as session:
            saved = MemoryEnrichmentRepository(session).complete(
                claim=claim,
                enrichment=result.enrichment,
                schema_version=result.schema_version,
                prompt_version=result.prompt_version,
                model=result.model,
            )

        if not saved:
            logger.info("Discarded stale enrichment for memory %s.", claim.memory_id)
    except Exception as exc:
        try:
            _mark_failed(
                claim,
                type(exc).__name__,
                retryable=_is_retryable(exc),
            )
        except Exception:
            logger.exception(
                "Could not persist failure for memory %s; its lease will expire.",
                claim.memory_id,
            )
        logger.exception(
            "Memory enrichment attempt %s failed for memory %s.",
            claim.attempt_count,
            claim.memory_id,
        )
    return True


def _load_claimed_content(claim: EnrichmentClaim) -> str | None:
    with SessionLocal() as session:
        memory = session.scalar(
            select(Memory).where(Memory.id == claim.memory_id)
        )
        if memory is None:
            return None
        return memory.content


def _mark_failed(
    claim: EnrichmentClaim,
    error_code: str,
    retryable: bool,
) -> None:
    with SessionLocal() as session:
        MemoryEnrichmentRepository(session).fail(
            claim=claim,
            error_code=error_code,
            retryable=retryable,
        )


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, MemoryEnrichmentProviderError):
        return error.retryable
    if isinstance(error, MemoryEnrichmentIncompleteError):
        return True
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    return False


async def run_memory_enrichment_worker() -> None:
    """Poll persisted work so pending jobs and retries survive restarts."""
    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        try:
            with SessionLocal() as session:
                MemoryEnrichmentRepository(
                    session
                ).fail_expired_final_attempts()

            processed = await process_memory_enrichment()
            if processed:
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Memory enrichment worker iteration failed.")

