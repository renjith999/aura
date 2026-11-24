import asyncio
import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import OpenAIModelPricing, settings
from app.models.base import Base
from app.models.memory import Memory
from app.models.memory_enrichment import MemoryEnrichment
from app.models.memory_enrichment_attempt import MemoryEnrichmentAttempt
from app.models.memory_enrichment_override import MemoryEnrichmentOverride
from app.repositories.memory_enrichment_repository import (
    MemoryEnrichmentRepository,
)
from app.schemas.memory_enrichment import MemoryEnrichmentV1
from app.services.enrichment_cost import UsageCounts
from app.services.memory_enrichment_service import (
    EnrichmentAttemptData,
    MemoryEnrichmentIncompleteError,
    MemoryEnrichmentProviderError,
    MemoryEnrichmentRefusalError,
    MemoryEnrichmentService,
    MemoryEnrichmentValidationError,
)
from app.services.memory_enrichment_tasks import process_memory_enrichment


@pytest.fixture
def task_session_factory(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'memory-enrichment-tasks.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        "app.services.memory_enrichment_tasks.SessionLocal",
        session_factory,
    )
    try:
        yield session_factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_pending_memory(session_factory):
    with session_factory() as session:
        memory = Memory(
            title="Task test",
            content="Keep this user text unchanged.",
            user_id="user-1",
        )
        session.add(memory)
        session.flush()
        MemoryEnrichmentRepository(session).create_or_reset_pending(
            memory_id=memory.id,
            content=memory.content,
            schema_version="1.0.0",
            prompt_version="1.4.0",
            model="gpt-5-mini",
        )
        session.commit()
        return memory.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,retryable",
    [
        (MemoryEnrichmentProviderError("provider unavailable", retryable=True), True),
        (MemoryEnrichmentIncompleteError("incomplete response"), True),
        (TimeoutError("request timed out"), True),
        (MemoryEnrichmentRefusalError("refused"), False),
        (MemoryEnrichmentValidationError("invalid output"), False),
        (MemoryEnrichmentProviderError("bad request", retryable=False), False),
    ],
)
async def test_worker_records_retryable_and_terminal_failures(
    task_session_factory,
    failure,
    retryable,
):
    memory_id = create_pending_memory(task_session_factory)

    class FailingEnrichmentService:
        async def enrich_with_metadata(self, content):
            assert content == "Keep this user text unchanged."
            raise failure

    processed = await process_memory_enrichment(
        memory_id,
        FailingEnrichmentService,
    )

    assert processed is True
    with task_session_factory() as session:
        memory = session.get(Memory, memory_id)
        enrichment = session.get(MemoryEnrichment, memory_id)

        assert memory is not None
        assert memory.content == "Keep this user text unchanged."
        assert enrichment is not None
        assert enrichment.status == "failed"
        assert enrichment.attempt_count == 1
        assert enrichment.last_error == type(failure).__name__
        attempt = (
            session.query(MemoryEnrichmentAttempt).filter_by(memory_id=memory_id).one()
        )
        assert attempt.outcome in {
            "provider_error",
            "incomplete",
            "transport_error",
            "refused",
            "validation_error",
        }
        assert attempt.input_tokens is None
        assert attempt.output_tokens is None
        assert attempt.cost_estimate is None
        if retryable:
            assert enrichment.next_retry_at is not None
        else:
            assert enrichment.next_retry_at is None


@pytest.mark.asyncio
async def test_worker_discards_claim_when_source_content_hash_is_stale(
    task_session_factory,
):
    memory_id = create_pending_memory(task_session_factory)
    with task_session_factory() as session:
        session.add(
            MemoryEnrichmentOverride(
                memory_id=memory_id,
                overrides={"summary": "User corrected summary."},
            )
        )
        session.commit()

    with task_session_factory() as session:
        memory = session.get(Memory, memory_id)
        assert memory is not None
        memory.content = "Changed while the job was pending."
        session.commit()

    class UnexpectedEnrichmentService:
        async def enrich_with_metadata(self, content):
            pytest.fail("Stale source text must not reach the model service")

    await process_memory_enrichment(memory_id, UnexpectedEnrichmentService)

    with task_session_factory() as session:
        memory = session.get(Memory, memory_id)
        enrichment = session.get(MemoryEnrichment, memory_id)

        assert memory is not None
        assert memory.content == "Changed while the job was pending."
        assert enrichment is not None
        assert enrichment.status == "failed"
        assert enrichment.last_error == "source_content_changed"
        assert hashlib.sha256(memory.content.encode("utf-8")).hexdigest() != (
            enrichment.source_content_hash
        )


@pytest.mark.asyncio
async def test_worker_persists_successful_usage_and_cost_without_changing_memory(
    task_session_factory,
    monkeypatch,
):
    memory_id = create_pending_memory(task_session_factory)
    with task_session_factory() as session:
        session.add(
            MemoryEnrichmentOverride(
                memory_id=memory_id,
                overrides={"summary": "User corrected summary."},
            )
        )
        session.commit()
    monkeypatch.setattr(
        settings,
        "openai_model_pricing",
        {
            "gpt-5-mini-2026-01-01": OpenAIModelPricing(
                input_per_million=Decimal("1.25"),
                output_per_million=Decimal("4.50"),
            )
        },
    )
    monkeypatch.setattr(settings, "openai_pricing_version", "test-pricing-v1")
    attempt_data = EnrichmentAttemptData(
        response_model="gpt-5-mini-2026-01-01",
        provider_status="completed",
        response_id="resp-success",
        request_id="req-success",
        usage=UsageCounts(
            input_tokens=1_000,
            output_tokens=200,
            total_tokens=1_200,
        ),
        response_received_at=datetime.now(UTC),
    )

    class SuccessfulService:
        async def enrich_with_metadata(self, content):
            assert content == "Keep this user text unchanged."
            return SimpleNamespace(
                enrichment=MemoryEnrichmentV1(
                    summary="A short summary.",
                    category="work",
                    memory_type="fact",
                    tags=["test"],
                    entities=[],
                    importance=3,
                ),
                schema_version="1.0.0",
                prompt_version="1.4.0",
                model="gpt-5-mini",
                attempt=attempt_data,
            )

    assert await process_memory_enrichment(memory_id, SuccessfulService) is True

    with task_session_factory() as session:
        memory = session.get(Memory, memory_id)
        attempts = list(
            session.query(MemoryEnrichmentAttempt).filter_by(memory_id=memory_id).all()
        )
        assert memory is not None
        assert memory.content == "Keep this user text unchanged."
        assert len(attempts) == 1
        attempt = attempts[0]
        override = session.get(MemoryEnrichmentOverride, memory_id)
        enrichment = session.get(MemoryEnrichment, memory_id)
        assert attempt.outcome == "completed"
        assert attempt.response_id == "resp-success"
        assert attempt.request_id == "req-success"
        assert attempt.response_model == "gpt-5-mini-2026-01-01"
        assert attempt.input_tokens == 1_000
        assert attempt.output_tokens == 200
        assert attempt.total_tokens == 1_200
        assert attempt.cost_estimate == Decimal("0.002150000000")
        assert attempt.pricing_version == "test-pricing-v1"
        assert enrichment is not None
        assert enrichment.summary == "A short summary."
        assert override is not None
        assert override.overrides["summary"] == "User corrected summary."


@pytest.mark.asyncio
async def test_worker_persists_usage_from_incomplete_retryable_response(
    task_session_factory,
):
    memory_id = create_pending_memory(task_session_factory)
    attempt_data = EnrichmentAttemptData(
        response_model="gpt-5-mini",
        provider_status="incomplete",
        response_id="resp-incomplete",
        request_id="req-incomplete",
        usage=UsageCounts(input_tokens=60, output_tokens=15, total_tokens=75),
        response_received_at=datetime.now(UTC),
    )

    class IncompleteService:
        async def enrich_with_metadata(self, content):
            raise MemoryEnrichmentIncompleteError(
                "incomplete response", attempt=attempt_data
            )

    assert await process_memory_enrichment(memory_id, IncompleteService) is True

    with task_session_factory() as session:
        memory = session.get(Memory, memory_id)
        attempt = (
            session.query(MemoryEnrichmentAttempt).filter_by(memory_id=memory_id).one()
        )
        enrichment = session.get(MemoryEnrichment, memory_id)
        assert memory is not None
        assert memory.content == "Keep this user text unchanged."
        assert enrichment is not None
        assert enrichment.status == "failed"
        assert enrichment.next_retry_at is not None
        assert attempt.outcome == "incomplete"
        assert attempt.input_tokens == 60
        assert attempt.output_tokens == 15


@pytest.mark.asyncio
async def test_actual_service_retry_keeps_attempts_and_pricing_snapshots(
    task_session_factory,
    monkeypatch,
):
    memory_id = create_pending_memory(task_session_factory)
    with task_session_factory() as session:
        session.add(
            MemoryEnrichmentOverride(
                memory_id=memory_id,
                overrides={"summary": "Manually preserved summary."},
            )
        )
        session.commit()

    monkeypatch.setattr(
        settings,
        "openai_model_pricing",
        {
            "gpt-5-mini": OpenAIModelPricing(
                input_per_million=Decimal("1"),
                output_per_million=Decimal("3"),
            )
        },
    )
    monkeypatch.setattr(settings, "openai_pricing_version", "snapshot-before-retry")
    success_json = MemoryEnrichmentV1(
        summary="AI summary after retry",
        category="work",
        memory_type="fact",
        tags=["retry"],
        entities=[],
        importance=3,
    ).model_dump_json()
    responses = [
        SimpleNamespace(
            id="resp-incomplete-retry",
            model="gpt-5-mini",
            status="incomplete",
            output_text="",
            output=[],
            usage=SimpleNamespace(
                input_tokens=60,
                output_tokens=15,
                total_tokens=75,
                input_tokens_details=None,
                output_tokens_details=None,
            ),
        ),
        SimpleNamespace(
            id="resp-success-retry",
            model="gpt-5-mini",
            status="completed",
            output_text=success_json,
            output=[],
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
                input_tokens_details=None,
                output_tokens_details=None,
            ),
        ),
    ]

    class RawResponses:
        def __init__(self):
            self.index = 0

        async def create(self, **_kwargs):
            response = responses[self.index]
            self.index += 1
            return SimpleNamespace(
                headers={"x-request-id": f"req-{response.id}"},
                parse=lambda: response,
            )

    mock_client = SimpleNamespace(
        responses=SimpleNamespace(with_raw_response=RawResponses())
    )

    def service_factory():
        return MemoryEnrichmentService(client=mock_client)

    assert await process_memory_enrichment(memory_id, service_factory) is True
    with task_session_factory() as session:
        job = session.get(MemoryEnrichment, memory_id)
        first = (
            session.query(MemoryEnrichmentAttempt).filter_by(memory_id=memory_id).one()
        )
        assert job is not None and job.status == "failed"
        assert first.outcome == "incomplete"
        assert first.input_tokens == 60 and first.output_tokens == 15
        assert first.cost_estimate == Decimal("0.000105000000")
        assert first.pricing_version == "snapshot-before-retry"
        job.next_retry_at = datetime.now(UTC).replace(year=2020)
        session.commit()

    monkeypatch.setattr(
        settings,
        "openai_model_pricing",
        {
            "gpt-5-mini": OpenAIModelPricing(
                input_per_million=Decimal("2"),
                output_per_million=Decimal("6"),
            )
        },
    )
    monkeypatch.setattr(settings, "openai_pricing_version", "snapshot-after-retry")
    assert await process_memory_enrichment(memory_id, service_factory) is True

    with task_session_factory() as session:
        job = session.get(MemoryEnrichment, memory_id)
        memory = session.get(Memory, memory_id)
        override = session.get(MemoryEnrichmentOverride, memory_id)
        attempts = (
            session.query(MemoryEnrichmentAttempt)
            .filter_by(memory_id=memory_id)
            .order_by(MemoryEnrichmentAttempt.attempt_number)
            .all()
        )
        assert job is not None and job.status == "completed"
        assert job.attempt_count == 2
        assert memory is not None
        assert memory.content == "Keep this user text unchanged."
        assert override is not None
        assert override.overrides["summary"] == "Manually preserved summary."
        assert len(attempts) == 2
        assert [attempt.attempt_number for attempt in attempts] == [1, 2]
        assert attempts[0].pricing_version == "snapshot-before-retry"
        assert attempts[0].input_rate_per_million == Decimal("1")
        assert attempts[0].cost_estimate == Decimal("0.000105000000")
        assert attempts[1].pricing_version == "snapshot-after-retry"
        assert attempts[1].input_rate_per_million == Decimal("2")
        assert attempts[1].cost_estimate == Decimal("0.000320000000")
        assert sum(attempt.total_tokens or 0 for attempt in attempts) == 195


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output_text", "output_item", "expected_outcome"),
    [
        (
            "{}",
            SimpleNamespace(content=[SimpleNamespace(type="refusal")]),
            "refused",
        ),
        ("{invalid", SimpleNamespace(content=[]), "validation_error"),
    ],
)
async def test_actual_service_persists_usage_for_terminal_provider_results(
    task_session_factory,
    output_text,
    output_item,
    expected_outcome,
):
    memory_id = create_pending_memory(task_session_factory)
    response = SimpleNamespace(
        id=f"resp-{expected_outcome}",
        model="gpt-5-mini",
        status="completed",
        output_text=output_text,
        output=[output_item],
        usage=SimpleNamespace(
            input_tokens=40,
            output_tokens=10,
            total_tokens=50,
            input_tokens_details=None,
            output_tokens_details=None,
        ),
    )

    class RawResponses:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                headers={"x-request-id": f"req-{expected_outcome}"},
                parse=lambda: response,
            )

    mock_client = SimpleNamespace(
        responses=SimpleNamespace(with_raw_response=RawResponses())
    )

    def service_factory():
        return MemoryEnrichmentService(client=mock_client)

    assert await process_memory_enrichment(memory_id, service_factory) is True

    with task_session_factory() as session:
        job = session.get(MemoryEnrichment, memory_id)
        attempt = (
            session.query(MemoryEnrichmentAttempt).filter_by(memory_id=memory_id).one()
        )
        assert job is not None and job.status == "failed"
        assert job.next_retry_at is None
        assert attempt.outcome == expected_outcome
        assert attempt.response_id == f"resp-{expected_outcome}"
        assert attempt.request_id == f"req-{expected_outcome}"
        assert attempt.input_tokens == 40
        assert attempt.output_tokens == 10
        assert attempt.total_tokens == 50
        assert attempt.cost_estimate is None


@pytest.mark.asyncio
async def test_stale_provider_response_is_rejected_but_usage_is_retained(
    task_session_factory,
):
    memory_id = create_pending_memory(task_session_factory)
    entered = asyncio.Event()
    release = asyncio.Event()
    response = SimpleNamespace(
        id="resp-stale-content",
        model="gpt-5-mini",
        status="completed",
        output_text=MemoryEnrichmentV1(
            summary="Must not replace the new generation",
            category="work",
            memory_type="fact",
            tags=[],
            entities=[],
            importance=3,
        ).model_dump_json(),
        output=[],
        usage=SimpleNamespace(
            input_tokens=80,
            output_tokens=20,
            total_tokens=100,
            input_tokens_details=None,
            output_tokens_details=None,
        ),
    )

    class RawResponses:
        async def create(self, **_kwargs):
            entered.set()
            await release.wait()
            return SimpleNamespace(
                headers={"x-request-id": "req-stale-content"},
                parse=lambda: response,
            )

    mock_client = SimpleNamespace(
        responses=SimpleNamespace(with_raw_response=RawResponses())
    )

    def service_factory():
        return MemoryEnrichmentService(client=mock_client)

    running = asyncio.create_task(process_memory_enrichment(memory_id, service_factory))
    await asyncio.wait_for(entered.wait(), timeout=2)
    with task_session_factory() as session:
        memory = session.get(Memory, memory_id)
        current = session.get(MemoryEnrichment, memory_id)
        assert memory is not None and current is not None
        memory.content = "User edited this while enrichment was running."
        new_generation = (
            MemoryEnrichmentRepository(session)
            .create_or_reset_pending(
                memory_id,
                memory.content,
                schema_version="1.0.0",
                prompt_version="1.4.0",
                model="gpt-5-mini",
            )
            .generation_id
        )
        session.commit()

    release.set()
    assert await running is True
    with task_session_factory() as session:
        memory = session.get(Memory, memory_id)
        current = session.get(MemoryEnrichment, memory_id)
        attempt = (
            session.query(MemoryEnrichmentAttempt).filter_by(memory_id=memory_id).one()
        )
        assert memory is not None
        assert memory.content == "User edited this while enrichment was running."
        assert current is not None and current.status == "pending"
        assert current.generation_id == new_generation
        assert current.summary is None
        assert attempt.outcome == "completed"
        assert attempt.response_id == "resp-stale-content"
        assert attempt.request_id == "req-stale-content"
        assert attempt.total_tokens == 100
