import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import get_current_user_id
from app.core.database import get_db_session
from app.main import app
from app.models.base import Base


@pytest.fixture
def memory_client(tmp_path, monkeypatch):
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if test_database_url:
        test_engine = create_engine(test_database_url, pool_pre_ping=True)
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

    def override_session():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user_id] = lambda: identity["user_id"]
    with TestClient(app) as client:
        yield client, identity
    app.dependency_overrides.clear()
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


def test_create_and_retrieve_memory_preserves_text_and_timestamps(memory_client):
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


def test_list_supports_keyword_category_and_favorite_filters(memory_client):
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
        json={"title": "Updated note", "is_favorite": True},
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
def test_validation_rejects_blank_or_empty_updates(memory_client, method, payload):
    client, _ = memory_client
    response = (
        client.post("/memories", json=payload)
        if method == "post"
        else client.patch("/memories/not-an-id", json=payload)
    )
    assert response.status_code == 422


def test_unknown_ids_return_not_found_for_get_update_and_delete(memory_client):
    client, _ = memory_client
    assert client.get("/memories/missing").status_code == 404
    assert (
        client.patch("/memories/missing", json={"title": "Update"}).status_code == 404
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
