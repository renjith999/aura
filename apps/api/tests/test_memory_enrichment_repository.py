
import hashlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.memory import Memory
from app.models.memory_enrichment import MemoryEnrichment
from app.repositories.memory_enrichment_repository import (
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
            select(MemoryEnrichment).where(
                MemoryEnrichment.memory_id == memory.id
            )
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
    assert enrichment_session.get(
        MemoryEnrichment,
        "missing-memory-id",
    ) is None


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
        isinstance(entity["name"], str)
        and isinstance(entity["entity_type"], str)
        for entity in record.entities
    )
