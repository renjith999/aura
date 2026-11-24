import os
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import get_current_user_id
from app.core.config import OpenAIModelPricing, settings
from app.core.database import get_db_session
from app.main import app
from app.models.base import Base
from app.models.memory import Memory
from app.models.memory_enrichment import MemoryEnrichment
from app.models.memory_enrichment_attempt import MemoryEnrichmentAttempt
from app.models.memory_enrichment_override import MemoryEnrichmentOverride
from app.schemas.memory_enrichment import MemoryEnrichmentV1
from app.services.memory_enrichment_service import MemoryEnrichmentService


def create_enrichment_result():
    """Return a valid enrichment result for background task tests."""
    return SimpleNamespace(
        enrichment=MemoryEnrichmentV1(
            summary="Test memory summary",
            category=None,
            memory_type=None,
            tags=["test-memory"],
            entities=[],
            importance=3,
        ),
        schema_version="1.0.0",
        prompt_version="1.4.0",
        model="gpt-5-mini",
    )


@pytest.fixture
def memory_client(tmp_path, monkeypatch):
    test_database_url = os.getenv("TEST_DATABASE_URL")

    if test_database_url:
        test_engine = create_engine(
            test_database_url,
            pool_pre_ping=True,
        )
    else:
        test_engine = create_engine(
            f"sqlite:///{tmp_path / 'memories.db'}",
            connect_args={"check_same_thread": False},
        )

    Base.metadata.create_all(test_engine)

    test_session = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    identity = {"user_id": "user-1"}

    class NoopEnrichmentService:
        MODEL = "gpt-5-mini"

        async def enrich_with_metadata(self, content):
            return create_enrichment_result()

    monkeypatch.setattr(
        "app.api.routes.memories.MemoryEnrichmentService",
        NoopEnrichmentService,
    )

    # Background enrichment must use the test database,
    # not the application's configured database.
    monkeypatch.setattr(
        "app.services.memory_enrichment_tasks.SessionLocal",
        test_session,
    )
    monkeypatch.setattr(
        "app.services.memory_enrichment_tasks.POLL_INTERVAL_SECONDS",
        3600.0,
    )

    def override_session():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user_id] = lambda: identity["user_id"]
    app.state.test_session_factory = test_session

    try:
        with TestClient(app) as client:
            yield client, identity
    finally:
        app.dependency_overrides.clear()
        del app.state.test_session_factory
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


def create_memory(client, **overrides):
    payload = {
        "title": "Project note",
        "content": "  Keep this text exactly.\n ",
        "category": "work",
        "is_favorite": False,
    }
    payload.update(overrides)

    return client.post("/memories", json=payload)


def test_create_and_retrieve_memory_preserves_text_and_timestamps(
    memory_client,
):
    client, _ = memory_client

    created = create_memory(client)

    assert created.status_code == 201

    data = created.json()

    assert data["id"]
    assert data["content"] == "  Keep this text exactly.\n "
    assert data["created_at"]
    assert data["updated_at"]

    retrieved = client.get(f"/memories/{data['id']}")

    assert retrieved.status_code == 200
    assert retrieved.json() == data


def test_create_schedules_and_runs_enrichment_without_changing_memory(
    memory_client,
    monkeypatch,
):
    client, _ = memory_client
    enriched_contents = []

    class FakeEnrichmentService:
        async def enrich_with_metadata(self, content):
            enriched_contents.append(content)
            return create_enrichment_result()

    monkeypatch.setattr(
        "app.api.routes.memories.MemoryEnrichmentService",
        FakeEnrichmentService,
    )

    response = create_memory(client)

    assert response.status_code == 201
    assert response.json()["content"] == "  Keep this text exactly.\n "
    assert enriched_contents == ["  Keep this text exactly.\n "]
    status_response = client.get(f"/memories/{response.json()['id']}/enrichment")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert status_response.json()["attempt_count"] == 1


def test_authenticated_api_to_real_service_worker_persists_enrichment_and_usage(
    memory_client,
    monkeypatch,
):
    """Exercise route, actual service, worker, repositories and readback together."""
    client, _ = memory_client
    response_payload = MemoryEnrichmentV1(
        summary="Provider generated summary",
        category="project",
        memory_type="fact",
        tags=["aura", "integration"],
        entities=[{"name": "Aura", "entity_type": "product"}],
        importance=4,
    ).model_dump_json()
    raw_response = SimpleNamespace(
        headers={"x-request-id": "req-aura62-integration"},
        parse=lambda: SimpleNamespace(
            id="resp-aura62-integration",
            model="gpt-5-mini-2026-01-01",
            status="completed",
            output_text=response_payload,
            output=[],
            usage=SimpleNamespace(
                input_tokens=1000,
                output_tokens=200,
                total_tokens=1200,
                input_tokens_details=SimpleNamespace(cached_tokens=125),
                output_tokens_details=SimpleNamespace(reasoning_tokens=30),
            ),
        ),
    )

    class RawResponses:
        async def create(self, **_kwargs):
            return raw_response

    mock_client = SimpleNamespace(
        responses=SimpleNamespace(with_raw_response=RawResponses())
    )
    monkeypatch.setattr(
        "app.api.routes.memories.MemoryEnrichmentService",
        lambda: MemoryEnrichmentService(client=mock_client),
    )
    monkeypatch.setattr(
        settings,
        "openai_model_pricing",
        {
            "gpt-5-mini-2026-01-01": OpenAIModelPricing(
                input_per_million=Decimal("1.25"),
                output_per_million=Decimal("4.50"),
                cached_input_per_million=Decimal("0.125"),
            )
        },
    )
    monkeypatch.setattr(settings, "openai_pricing_version", "aura62-integration-v1")

    original_content = "  User supplied project text.\n"
    created = create_memory(client, content=original_content)
    assert created.status_code == 201
    memory_id = created.json()["id"]
    assert created.json()["content"] == original_content

    readback = client.get(f"/memories/{memory_id}/enrichment")
    assert readback.status_code == 200
    enrichment_payload = readback.json()
    assert enrichment_payload == {
        "memory_id": memory_id,
        "status": "completed",
        "attempt_count": 1,
        "last_error": None,
        "next_retry_at": None,
        "completed_at": enrichment_payload["completed_at"],
        "summary": "Provider generated summary",
        "category": "project",
        "memory_type": "fact",
        "tags": ["aura", "integration"],
        "entities": [{"name": "Aura", "entity_type": "product"}],
        "importance": 4,
        "manual_fields": [],
    }
    assert enrichment_payload["completed_at"] is not None
    assert client.get(f"/memories/{memory_id}").json()["content"] == original_content

    corrected = client.patch(
        f"/memories/{memory_id}/enrichment",
        json={"summary": "Manually corrected summary."},
    )
    assert corrected.status_code == 200
    assert corrected.json()["summary"] == "Manually corrected summary."
    assert corrected.json()["manual_fields"] == ["summary"]

    with client.app.state.test_session_factory() as session:
        attempt = (
            session.query(MemoryEnrichmentAttempt).filter_by(memory_id=memory_id).one()
        )
        assert attempt.outcome == "completed"
        assert attempt.requested_model == "gpt-5-mini"
        assert attempt.response_model == "gpt-5-mini-2026-01-01"
        assert attempt.response_id == "resp-aura62-integration"
        assert attempt.request_id == "req-aura62-integration"
        assert (attempt.input_tokens, attempt.output_tokens, attempt.total_tokens) == (
            1000,
            200,
            1200,
        )
        assert attempt.cached_input_tokens == 125
        assert attempt.reasoning_output_tokens == 30
        assert attempt.cost_estimate == Decimal("0.002009375000")
        assert attempt.pricing_version == "aura62-integration-v1"
        enrichment = session.get(MemoryEnrichment, memory_id)
        assert enrichment is not None
        assert enrichment.summary == "Provider generated summary"
        memory = session.get(Memory, memory_id)
        assert memory is not None
        assert memory.content == original_content


def test_api_enrichment_status_and_content_update_reenrichment(
    memory_client,
    monkeypatch,
):
    client, _ = memory_client
    expected_enrichment = create_enrichment_result()

    from app.services import memory_enrichment_tasks

    class FakeEnrichmentService:
        async def enrich_with_metadata(self, content):
            if content == "  Keep this text exactly.\n ":
                return expected_enrichment
            return SimpleNamespace(
                enrichment=MemoryEnrichmentV1(
                    summary="Updated memory summary",
                    category=None,
                    memory_type=None,
                    tags=["updated-memory"],
                    entities=[],
                    importance=3,
                ),
                schema_version="1.0.0",
                prompt_version="1.4.0",
                model="gpt-5-mini",
            )

    monkeypatch.setattr(
        "app.api.routes.memories.MemoryEnrichmentService",
        FakeEnrichmentService,
    )

    created = create_memory(client)

    assert created.status_code == 201
    memory_id = created.json()["id"]
    original_content = created.json()["content"]
    assert original_content == "  Keep this text exactly.\n "

    with memory_enrichment_tasks.SessionLocal() as session:
        memory = session.get(Memory, memory_id)
        enrichment = session.get(MemoryEnrichment, memory_id)

        assert memory is not None
        assert memory.content == original_content
        assert enrichment is not None
        assert enrichment.summary == "Test memory summary"
        assert enrichment.category is None
        assert enrichment.memory_type is None
        assert enrichment.tags == ["test-memory"]
        assert enrichment.entities == []
        assert enrichment.importance == 3
        assert enrichment.schema_version == "1.0.0"
        assert enrichment.prompt_version == "1.4.0"
        assert enrichment.model == "gpt-5-mini"
        assert len(enrichment.source_content_hash) == 64

    updated = client.patch(
        f"/memories/{memory_id}",
        json={"content": "Updated memory content."},
    )

    assert updated.status_code == 200
    assert updated.json()["content"] == "Updated memory content."

    with memory_enrichment_tasks.SessionLocal() as session:
        memory = session.get(Memory, memory_id)
        enrichment = session.get(MemoryEnrichment, memory_id)

        assert memory is not None
        assert memory.content == "Updated memory content."
        assert enrichment is not None
        assert enrichment.status == "completed"
        assert enrichment.summary == "Updated memory summary"


def test_enrichment_failure_does_not_fail_memory_creation(
    memory_client,
    monkeypatch,
):
    client, _ = memory_client

    class FailingEnrichmentService:
        async def enrich_with_metadata(self, content):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "app.api.routes.memories.MemoryEnrichmentService",
        FailingEnrichmentService,
    )

    response = create_memory(client)

    assert response.status_code == 201
    assert response.json()["content"] == "  Keep this text exactly.\n "

    retrieved = client.get(f"/memories/{response.json()['id']}")

    assert retrieved.status_code == 200
    assert retrieved.json()["content"] == "  Keep this text exactly.\n "

    status_response = client.get(f"/memories/{response.json()['id']}/enrichment")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "failed"
    assert status_response.json()["attempt_count"] == 1
    assert status_response.json()["last_error"] == "RuntimeError"


def test_list_supports_keyword_category_and_favorite_filters(
    memory_client,
):
    client, _ = memory_client

    create_memory(client)

    favorite = create_memory(
        client,
        title="Another item",
        content="Read about FastAPI",
        category="learning",
        is_favorite=True,
    ).json()

    all_memories = client.get("/memories")

    assert all_memories.status_code == 200
    assert len(all_memories.json()) == 2

    assert client.get("/memories?query=FastAPI").json() == [favorite]

    assert client.get("/memories?category=work").json()[0]["category"] == "work"

    assert client.get("/memories?is_favorite=true").json() == [favorite]


def test_empty_list_is_successful(memory_client):
    client, _ = memory_client

    assert client.get("/memories").status_code == 200
    assert client.get("/memories").json() == []


def test_update_changes_fields_and_updated_timestamp(memory_client):
    client, _ = memory_client

    original = create_memory(client).json()

    response = client.patch(
        f"/memories/{original['id']}",
        json={
            "title": "Updated note",
            "is_favorite": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated note"
    assert response.json()["is_favorite"] is True
    assert response.json()["content"] == original["content"]
    assert response.json()["updated_at"] >= original["updated_at"]


def test_delete_removes_memory(memory_client):
    client, _ = memory_client

    memory_id = create_memory(client).json()["id"]

    deleted = client.delete(f"/memories/{memory_id}")

    assert deleted.status_code == 204
    assert client.get(f"/memories/{memory_id}").status_code == 404


@pytest.mark.parametrize(
    "method,payload",
    [
        ("post", {"title": "  ", "content": "content"}),
        ("post", {"title": "title", "content": "   "}),
        ("patch", {}),
    ],
)
def test_validation_rejects_blank_or_empty_updates(
    memory_client,
    method,
    payload,
):
    client, _ = memory_client

    response = (
        client.post("/memories", json=payload)
        if method == "post"
        else client.patch("/memories/not-an-id", json=payload)
    )

    assert response.status_code == 422


def test_unknown_ids_return_not_found_for_get_update_and_delete(
    memory_client,
):
    client, _ = memory_client

    assert client.get("/memories/missing").status_code == 404

    assert (
        client.patch(
            "/memories/missing",
            json={"title": "Update"},
        ).status_code
        == 404
    )

    assert client.delete("/memories/missing").status_code == 404


def test_memories_are_isolated_between_users(memory_client):
    client, identity = memory_client

    created = create_memory(client).json()

    identity["user_id"] = "user-2"

    assert client.get("/memories").json() == []
    assert client.get(f"/memories/{created['id']}").status_code == 404

    assert (
        client.patch(
            f"/memories/{created['id']}",
            json={"title": "Cross-user update"},
        ).status_code
        == 404
    )

    assert client.delete(f"/memories/{created['id']}").status_code == 404


def test_memory_routes_require_authenticated_user(memory_client):
    client, _ = memory_client

    app.dependency_overrides.pop(get_current_user_id)

    response = client.get("/memories")

    assert response.status_code == 401


def test_enrichment_status_is_scoped_to_memory_owner(memory_client):
    client, identity = memory_client
    created = create_memory(client).json()

    identity["user_id"] = "user-2"

    response = client.get(f"/memories/{created['id']}/enrichment")

    assert response.status_code == 404


def test_manual_enrichment_correction_preserves_source_and_ai_values(memory_client):
    client, _ = memory_client
    created = create_memory(client)
    memory_id = created.json()["id"]
    original_content = created.json()["content"]

    response = client.patch(
        f"/memories/{memory_id}/enrichment",
        json={
            "summary": "  Corrected by the user.  ",
            "category": "work",
            "memory_type": "preference",
            "tags": [" Work ", "WORK", "custom-tag"],
            "entities": [{"name": "  Aura  ", "entity_type": "product"}],
            "importance": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == "Corrected by the user."
    assert payload["category"] == "work"
    assert payload["memory_type"] == "preference"
    assert payload["tags"] == ["work", "custom-tag"]
    assert payload["entities"] == [{"name": "Aura", "entity_type": "product"}]
    assert payload["importance"] == 5
    assert payload["manual_fields"] == [
        "category",
        "entities",
        "importance",
        "memory_type",
        "summary",
        "tags",
    ]
    assert client.get(f"/memories/{memory_id}").json()["content"] == original_content

    with client.app.state.test_session_factory() as session:
        memory = session.get(Memory, memory_id)
        enrichment = session.get(MemoryEnrichment, memory_id)
        override = session.get(MemoryEnrichmentOverride, memory_id)
        assert memory is not None
        assert memory.content == original_content
        assert enrichment is not None
        assert enrichment.summary == "Test memory summary"
        assert enrichment.category is None
        assert enrichment.tags == ["test-memory"]
        assert override is not None
        assert override.overrides["summary"] == "Corrected by the user."


def test_manual_enrichment_correction_can_clear_and_reset_overrides(memory_client):
    client, _ = memory_client
    memory_id = create_memory(client).json()["id"]

    edited = client.patch(
        f"/memories/{memory_id}/enrichment",
        json={"summary": None, "tags": []},
    )
    assert edited.status_code == 200
    assert edited.json()["summary"] is None
    assert edited.json()["tags"] == []
    assert set(edited.json()["manual_fields"]) == {"summary", "tags"}

    reset = client.patch(
        f"/memories/{memory_id}/enrichment",
        json={"clear_overrides": ["summary", "tags"]},
    )
    assert reset.status_code == 200
    assert reset.json()["summary"] == "Test memory summary"
    assert reset.json()["tags"] == ["test-memory"]
    assert reset.json()["manual_fields"] == []


def test_manual_enrichment_override_survives_content_reenrichment(memory_client):
    client, _ = memory_client
    memory_id = create_memory(client).json()["id"]
    manual_summary = client.patch(
        f"/memories/{memory_id}/enrichment",
        json={"summary": "Keep my corrected summary."},
    )
    assert manual_summary.status_code == 200

    updated = client.patch(
        f"/memories/{memory_id}",
        json={"content": "Changed original memory text."},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "Changed original memory text."

    effective = client.get(f"/memories/{memory_id}/enrichment")
    assert effective.status_code == 200
    assert effective.json()["summary"] == "Keep my corrected summary."
    assert effective.json()["manual_fields"] == ["summary"]

    with client.app.state.test_session_factory() as session:
        memory = session.get(Memory, memory_id)
        enrichment = session.get(MemoryEnrichment, memory_id)
        assert memory is not None
        assert memory.content == "Changed original memory text."
        assert enrichment is not None
        assert enrichment.summary == "Test memory summary"


def test_manual_enrichment_correction_queues_missing_enrichment(memory_client):
    client, _ = memory_client
    with client.app.state.test_session_factory() as session:
        memory = Memory(
            title="Legacy memory",
            content="Original legacy text.",
            user_id="user-1",
        )
        session.add(memory)
        session.commit()
        memory_id = memory.id

    response = client.patch(
        f"/memories/{memory_id}/enrichment",
        json={"summary": "Manually added summary."},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    completed = client.get(f"/memories/{memory_id}/enrichment")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["summary"] == "Manually added summary."
    with client.app.state.test_session_factory() as session:
        memory = session.get(Memory, memory_id)
        assert memory is not None
        assert memory.content == "Original legacy text."


def test_manual_enrichment_correction_is_scoped_to_memory_owner(memory_client):
    client, identity = memory_client
    memory_id = create_memory(client).json()["id"]
    identity["user_id"] = "user-2"

    response = client.patch(
        f"/memories/{memory_id}/enrichment",
        json={"summary": "Someone else's memory."},
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"summary": "   "},
        {"summary": "x" * 501},
        {"category": "unsupported"},
        {"memory_type": "unsupported"},
        {"importance": 6},
        {"tags": ["x" * 65]},
        {"tags": ["  "]},
        {"tags": ["🔥"]},
        {"tags": None},
        {"entities": [{"name": "x" * 101, "entity_type": "person"}]},
        {"unexpected": "value"},
        {},
    ],
)
def test_manual_enrichment_correction_rejects_invalid_data(memory_client, payload):
    client, _ = memory_client
    memory_id = create_memory(client).json()["id"]

    response = client.patch(f"/memories/{memory_id}/enrichment", json=payload)

    assert response.status_code == 422


def test_list_ordering_is_stable_across_pages(memory_client):
    client, _ = memory_client
    notes = [create_memory(client, title=f"Note {index}").json() for index in range(3)]

    expected = sorted(notes, key=lambda note: note["id"])
    expected.sort(
        key=lambda note: datetime.fromisoformat(note["created_at"]),
        reverse=True,
    )
    expected_ids = [note["id"] for note in expected]

    first_page = client.get("/memories?limit=2")
    second_page = client.get("/memories?limit=2&offset=2")

    assert first_page.status_code == 200
    assert [note["id"] for note in first_page.json()] == expected_ids[:2]
    assert second_page.status_code == 200
    assert [note["id"] for note in second_page.json()] == expected_ids[2:]
    assert [note["id"] for note in client.get("/memories").json()] == expected_ids


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1"])
def test_list_rejects_invalid_pagination(memory_client, query):
    client, _ = memory_client

    response = client.get(f"/memories?{query}")

    assert response.status_code == 422
