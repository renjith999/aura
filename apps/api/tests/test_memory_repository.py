
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import pytest

from app.models.base import Base
from app.models.memory import Memory
from app.models.memory_enrichment import MemoryEnrichment
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryUpdate


@pytest.fixture
def repository_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'memory-repository.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    try:
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_test_memory(session: Session) -> Memory:
    memory = Memory(
        title="Original title",
        content="Original content",
        user_id="user-1",
    )
    session.add(memory)
    session.commit()
    session.refresh(memory)
    return memory


def create_test_enrichment(
    session: Session,
    memory_id: str,
) -> MemoryEnrichment:
    enrichment = MemoryEnrichment(
        memory_id=memory_id,
        summary="Original summary",
        category="work",
        memory_type="fact",
        tags=["project", "development"],
        entities=[
            {"name": "Python", "entity_type": "technology"}
        ],
        importance=3,
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
        source_content_hash="a" * 64,
    )
    session.add(enrichment)
    session.commit()
    session.refresh(enrichment)
    return enrichment


def test_content_update_deletes_existing_enrichment(repository_session):
    session = repository_session
    memory = create_test_memory(session)
    create_test_enrichment(session, memory.id)

    repository = MemoryRepository(session)

    updated = repository.update(
        memory,
        MemoryUpdate(content="Updated content"),
    )

    assert updated.content == "Updated content"

    enrichment = session.get(MemoryEnrichment, memory.id)
    assert enrichment is None


def test_title_update_preserves_existing_enrichment(repository_session):
    session = repository_session
    memory = create_test_memory(session)
    create_test_enrichment(session, memory.id)

    repository = MemoryRepository(session)

    updated = repository.update(
        memory,
        MemoryUpdate(title="Updated title"),
    )

    assert updated.title == "Updated title"
    assert session.get(MemoryEnrichment, memory.id) is not None


def test_favorite_update_preserves_existing_enrichment(repository_session):
    session = repository_session
    memory = create_test_memory(session)
    create_test_enrichment(session, memory.id)

    repository = MemoryRepository(session)

    updated = repository.update(
        memory,
        MemoryUpdate(is_favorite=True),
    )

    assert updated.is_favorite is True
    assert session.get(MemoryEnrichment, memory.id) is not None


def test_unchanged_content_preserves_existing_enrichment(repository_session):
    session = repository_session
    memory = create_test_memory(session)
    create_test_enrichment(session, memory.id)

    repository = MemoryRepository(session)

    updated = repository.update(
        memory,
        MemoryUpdate(content=memory.content),
    )

    assert updated.content == "Original content"
    assert session.get(MemoryEnrichment, memory.id) is not None


def test_failed_update_rolls_back_enrichment_deletion(
    repository_session,
    monkeypatch,
):
    session = repository_session
    memory = create_test_memory(session)
    create_test_enrichment(session, memory.id)

    repository = MemoryRepository(session)

    def fail_commit():
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="Simulated database failure"):
        repository.update(
            memory,
            MemoryUpdate(content="Updated content"),
        )

    # Verify persisted state using a separate session.
    session.rollback()
    session.expire_all()

    persisted_memory = session.get(Memory, memory.id)
    persisted_enrichment = session.get(MemoryEnrichment, memory.id)

    assert persisted_memory is not None
    assert persisted_memory.content == "Original content"
    assert persisted_enrichment is not None
    assert persisted_enrichment.summary == "Original summary"
