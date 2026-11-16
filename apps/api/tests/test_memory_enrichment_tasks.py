import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.memory import Memory
from app.models.memory_enrichment import MemoryEnrichment
from app.repositories.memory_enrichment_repository import (
    MemoryEnrichmentRepository,
)
from app.services.memory_enrichment_service import (
    MemoryEnrichmentIncompleteError,
    MemoryEnrichmentProviderError,
    MemoryEnrichmentRefusalError,
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
