import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.memory import Memory
from app.models.memory_enrichment import MemoryEnrichment
from app.models.memory_enrichment_attempt import MemoryEnrichmentAttempt
from app.repositories.memory_enrichment_repository import (
    LEASE_SECONDS,
    MAX_ATTEMPTS,
    MemoryEnrichmentRepository,
)
from app.schemas.memory_enrichment import (
    EntityType,
    MemoryCategory,
    MemoryEnrichmentV1,
    MemoryEntity,
    MemoryType,
)


@pytest.fixture
def enrichment_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'memory-enrichment-repository.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    try:
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_memory(session: Session, content: str = "Original memory content"):
    memory = Memory(
        title="Test memory",
        content=content,
        user_id="user-1",
    )
    session.add(memory)
    session.commit()
    session.refresh(memory)
    return memory


def create_enrichment() -> MemoryEnrichmentV1:
    return MemoryEnrichmentV1(
        summary="A memory about software development.",
        category=MemoryCategory.WORK,
        memory_type=MemoryType.FACT,
        tags=["software-development", "python"],
        entities=[
            MemoryEntity(
                name="Python",
                entity_type=EntityType.TECHNOLOGY,
            ),
            MemoryEntity(
                name="FastAPI",
                entity_type=EntityType.TECHNOLOGY,
            ),
        ],
        importance=4,
    )


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def save_enrichment(
    session: Session,
    memory: Memory,
    enrichment: MemoryEnrichmentV1,
    prompt_version: str = "1.4.0",
    model: str = "gpt-5-mini",
) -> bool:
    repository = MemoryEnrichmentRepository(session)

    return repository.save_if_memory_unchanged(
        memory_id=memory.id,
        source_content_hash=content_hash(memory.content),
        enrichment=enrichment,
        schema_version="1.0.0",
        prompt_version=prompt_version,
        model=model,
    )


def test_saves_enrichment_for_existing_memory(enrichment_session):
    session = enrichment_session
    memory = create_memory(session)

    saved = save_enrichment(
        session,
        memory,
        create_enrichment(),
    )

    assert saved is True

    record = session.get(MemoryEnrichment, memory.id)

    assert record is not None
    assert record.summary == "A memory about software development."
    assert record.category == "work"
    assert record.memory_type == "fact"
    assert record.tags == ["software-development", "python"]
    assert record.entities == [
        {"name": "Python", "entity_type": "technology"},
        {"name": "FastAPI", "entity_type": "technology"},
    ]
    assert record.importance == 4
    assert record.schema_version == "1.0.0"
    assert record.prompt_version == "1.4.0"
    assert record.model == "gpt-5-mini"
    assert record.source_content_hash == content_hash(memory.content)
    assert record.created_at is not None
    assert record.updated_at is not None

    # Original memory content must remain unchanged.
    assert session.get(Memory, memory.id).content == "Original memory content"


def test_updates_existing_enrichment_without_creating_duplicate(
    enrichment_session,
):
    session = enrichment_session
    memory = create_memory(session)

    save_enrichment(session, memory, create_enrichment())

    updated_enrichment = MemoryEnrichmentV1(
        summary="Updated summary.",
        category=MemoryCategory.LEARNING,
        memory_type=MemoryType.GOAL,
        tags=["learning", "python"],
        entities=[
            MemoryEntity(
                name="Python",
                entity_type=EntityType.TECHNOLOGY,
            )
        ],
        importance=5,
    )

    saved = save_enrichment(
        session,
        memory,
        updated_enrichment,
        prompt_version="1.5.0",
    )

    assert saved is True

    records = list(
        session.scalars(
            select(MemoryEnrichment).where(MemoryEnrichment.memory_id == memory.id)
        )
    )

    assert len(records) == 1
    assert records[0].summary == "Updated summary."
    assert records[0].category == "learning"
    assert records[0].memory_type == "goal"
    assert records[0].importance == 5
    assert records[0].prompt_version == "1.5.0"


def test_rejects_enrichment_when_memory_content_changed(enrichment_session):
    session = enrichment_session
    memory = create_memory(session)

    repository = MemoryEnrichmentRepository(session)

    stale_hash = content_hash(memory.content)

    memory.content = "Changed memory content"
    session.commit()

    saved = repository.save_if_memory_unchanged(
        memory_id=memory.id,
        source_content_hash=stale_hash,
        enrichment=create_enrichment(),
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )

    assert saved is False
    assert session.get(MemoryEnrichment, memory.id) is None
    assert session.get(Memory, memory.id).content == "Changed memory content"


def test_rejects_enrichment_when_memory_does_not_exist(enrichment_session):
    repository = MemoryEnrichmentRepository(enrichment_session)

    saved = repository.save_if_memory_unchanged(
        memory_id="missing-memory-id",
        source_content_hash=content_hash("Original memory content"),
        enrichment=create_enrichment(),
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )

    assert saved is False
    assert (
        enrichment_session.get(
            MemoryEnrichment,
            "missing-memory-id",
        )
        is None
    )


def test_persists_enrichment_metadata_and_entity_values(enrichment_session):
    session = enrichment_session
    memory = create_memory(session)

    saved = save_enrichment(
        session,
        memory,
        create_enrichment(),
    )

    assert saved is True

    record = session.get(MemoryEnrichment, memory.id)

    assert record is not None
    assert record.schema_version == "1.0.0"
    assert record.prompt_version == "1.4.0"
    assert record.model == "gpt-5-mini"
    assert isinstance(record.tags, list)
    assert isinstance(record.entities, list)
    assert all(
        isinstance(entity["name"], str) and isinstance(entity["entity_type"], str)
        for entity in record.entities
    )


def test_pending_enrichment_can_be_claimed_only_once(enrichment_session):
    session = enrichment_session
    memory = create_memory(session)
    repository = MemoryEnrichmentRepository(session)
    repository.create_or_reset_pending(
        memory.id,
        memory.content,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )
    session.commit()

    now = datetime.now(UTC)
    claim = repository.claim(memory.id, now=now)

    assert claim is not None
    assert claim.memory_id == memory.id
    assert claim.attempt_count == 1
    assert repository.claim(memory.id, now=now) is None

    record = session.get(MemoryEnrichment, memory.id)
    assert record is not None
    assert record.status == "processing"
    assert record.lease_expires_at is not None


def test_pending_record_at_attempt_limit_is_not_claimed(enrichment_session):
    session = enrichment_session
    memory = create_memory(session)
    record = MemoryEnrichment(
        memory_id=memory.id,
        summary=None,
        category=None,
        memory_type=None,
        tags=[],
        entities=[],
        importance=None,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
        source_content_hash=content_hash(memory.content),
        status="pending",
        attempt_count=MAX_ATTEMPTS,
    )
    session.add(record)
    session.commit()

    assert MemoryEnrichmentRepository(session).claim(memory.id) is None


def test_expired_worker_lease_can_be_reclaimed(enrichment_session):
    session = enrichment_session
    memory = create_memory(session)
    repository = MemoryEnrichmentRepository(session)
    repository.create_or_reset_pending(
        memory.id,
        memory.content,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )
    session.commit()

    now = datetime.now(UTC)
    first_claim = repository.claim(memory.id, now=now)
    assert first_claim is not None

    recovered_claim = repository.claim(
        memory.id,
        now=now + timedelta(seconds=LEASE_SECONDS + 1),
    )

    assert recovered_claim is not None
    assert recovered_claim.attempt_count == 2

    attempts = list(
        enrichment_session.scalars(
            select(MemoryEnrichmentAttempt)
            .where(MemoryEnrichmentAttempt.memory_id == memory.id)
            .order_by(MemoryEnrichmentAttempt.attempt_number)
        )
    )
    assert [attempt.outcome for attempt in attempts] == ["unknown", "started"]


def test_retry_creates_a_new_attempt_without_overwriting_prior_usage(
    enrichment_session,
):
    session = enrichment_session
    memory = create_memory(session)
    repository = MemoryEnrichmentRepository(session)
    repository.create_or_reset_pending(
        memory.id,
        memory.content,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )
    session.commit()

    now = datetime.now(UTC)
    first_claim = repository.claim(memory.id, now=now)
    assert first_claim is not None
    assert repository.fail(
        first_claim,
        error_code="provider_error",
        retryable=True,
        now=now,
    )
    first_attempt = session.get(MemoryEnrichmentAttempt, first_claim.attempt_id)
    assert first_attempt is not None
    first_attempt.input_tokens = 25
    first_attempt.output_tokens = 5
    first_attempt.total_tokens = 30
    session.commit()

    retry_claim = repository.claim(
        memory.id,
        now=now + timedelta(seconds=40),
    )
    assert retry_claim is not None
    assert retry_claim.attempt_count == 2
    assert retry_claim.attempt_id != first_claim.attempt_id
    assert first_attempt.input_tokens == 25
    assert first_attempt.total_tokens == 30
    assert session.get(MemoryEnrichmentAttempt, retry_claim.attempt_id).outcome == (
        "started"
    )


def test_usage_persistence_is_idempotently_attached_to_claim(enrichment_session):
    session = enrichment_session
    memory = create_memory(session)
    repository = MemoryEnrichmentRepository(session)
    repository.create_or_reset_pending(
        memory.id,
        memory.content,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )
    session.commit()

    claim = repository.claim(memory.id)
    assert claim is not None
    assert session.get(MemoryEnrichmentAttempt, claim.attempt_id) is not None
    assert repository.claim(memory.id) is None
    attempts = list(
        session.scalars(
            select(MemoryEnrichmentAttempt).where(
                MemoryEnrichmentAttempt.generation_id == claim.generation_id
            )
        )
    )
    assert len(attempts) == 1


def test_content_reenrichment_keeps_historical_attempt_rows(enrichment_session):
    session = enrichment_session
    memory = create_memory(session)
    repository = MemoryEnrichmentRepository(session)
    repository.create_or_reset_pending(
        memory.id,
        memory.content,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )
    session.commit()
    first_claim = repository.claim(memory.id)
    assert first_claim is not None
    first_generation = first_claim.generation_id

    repository.create_or_reset_pending(
        memory.id,
        "Updated source content.",
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )
    session.commit()

    record = session.get(MemoryEnrichment, memory.id)
    old_attempt = session.get(MemoryEnrichmentAttempt, first_claim.attempt_id)
    assert record is not None
    assert record.generation_id != first_generation
    assert old_attempt is not None
    assert old_attempt.generation_id == first_generation


def test_memory_deletion_unlinks_but_retains_usage_attempt(enrichment_session):
    session = enrichment_session
    memory = create_memory(session)
    repository = MemoryEnrichmentRepository(session)
    repository.create_or_reset_pending(
        memory.id,
        memory.content,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )
    session.commit()
    claim = repository.claim(memory.id)
    assert claim is not None
    attempt = session.get(MemoryEnrichmentAttempt, claim.attempt_id)
    assert attempt is not None
    attempt.input_tokens = 70
    attempt.output_tokens = 10
    attempt.total_tokens = 80
    session.commit()

    session.delete(session.get(Memory, memory.id))
    session.commit()

    session.expire(attempt)
    retained = session.get(MemoryEnrichmentAttempt, claim.attempt_id)
    assert retained is not None
    assert retained.memory_id is None
    assert retained.input_tokens == 70
    assert retained.total_tokens == 80


def test_enrichment_and_usage_rollback_together_on_commit_failure(
    enrichment_session,
    monkeypatch,
):
    session = enrichment_session
    memory = create_memory(session)
    repository = MemoryEnrichmentRepository(session)
    repository.create_or_reset_pending(
        memory.id,
        memory.content,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )
    session.commit()
    claim = repository.claim(memory.id)
    assert claim is not None
    original_commit = session.commit

    def fail_commit():
        raise RuntimeError("simulated database commit failure")

    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated database commit failure"):
        repository.complete(
            claim,
            create_enrichment(),
            schema_version="1.0.0",
            prompt_version="1.4.0",
            model="gpt-5-mini",
        )
    monkeypatch.setattr(session, "commit", original_commit)
    session.expire_all()

    record = session.get(MemoryEnrichment, memory.id)
    attempt = session.get(MemoryEnrichmentAttempt, claim.attempt_id)
    assert record is not None
    assert record.status == "processing"
    assert record.summary is None
    assert attempt is not None
    assert attempt.outcome == "started"


def test_retry_schedule_is_bounded_and_exhausts_after_max_attempts(
    enrichment_session,
):
    session = enrichment_session
    memory = create_memory(session)
    repository = MemoryEnrichmentRepository(session)
    repository.create_or_reset_pending(
        memory.id,
        memory.content,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )
    session.commit()

    now = datetime.now(UTC)
    for expected_attempt, retry_delay in ((1, (4, 6)), (2, (24, 36))):
        claim = repository.claim(memory.id, now=now)
        assert claim is not None
        assert claim.attempt_count == expected_attempt
        assert repository.fail(
            claim,
            error_code="provider_error",
            retryable=True,
            now=now,
        )

        record = session.get(MemoryEnrichment, memory.id)
        assert record is not None
        assert record.status == "failed"
        assert record.next_retry_at is not None
        scheduled_at = record.next_retry_at
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=UTC)
        scheduled_delay = (scheduled_at - now).total_seconds()
        assert retry_delay[0] <= scheduled_delay <= retry_delay[1]
        now = scheduled_at + timedelta(seconds=1)

    final_claim = repository.claim(memory.id, now=now)
    assert final_claim is not None
    assert final_claim.attempt_count == MAX_ATTEMPTS
    assert repository.fail(
        final_claim,
        error_code="provider_error",
        retryable=True,
        now=now,
    )

    record = session.get(MemoryEnrichment, memory.id)
    assert record is not None
    assert record.status == "failed"
    assert record.next_retry_at is None
    assert repository.claim(memory.id, now=now + timedelta(days=1)) is None
