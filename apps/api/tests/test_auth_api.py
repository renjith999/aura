from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db_session
from app.core.security import utc_now
from app.main import app
from app.models.base import Base
from app.models.user import User, UserSession


@pytest.fixture
def auth_client(tmp_path):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(test_engine)
    test_session = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    def override_session():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as client:
        yield client, test_session
    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


def register(client, email="renji@example.com", password="correct horse battery"):
    return client.post("/auth/register", json={"email": email, "password": password})


def test_register_hashes_password_and_authenticates_memory_routes(auth_client):
    client, test_session = auth_client

    response = register(client)

    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["email"] == "renji@example.com"
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] > 0
    with test_session() as session:
        user = session.scalar(select(User))
        saved_session = session.scalar(select(UserSession))
        assert user is not None
        assert user.password_hash != "correct horse battery"
        assert user.password_hash.startswith("pbkdf2_sha256$")
        assert saved_session is not None
        assert saved_session.token_hash != payload["access_token"]

    created = client.post(
        "/memories",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
        json={"title": "Private", "content": "only this account can see me"},
    )
    assert created.status_code == 201


def test_duplicate_email_is_rejected_case_insensitively(auth_client):
    client, _ = auth_client
    assert register(client).status_code == 201

    duplicate = register(client, email="RENJI@example.com")

    assert duplicate.status_code == 409


def test_login_accepts_valid_credentials_and_rejects_invalid_credentials(auth_client):
    client, _ = auth_client
    register(client)

    valid = client.post(
        "/auth/login",
        json={"email": "RENJI@example.com", "password": "correct horse battery"},
    )
    invalid = client.post(
        "/auth/login",
        json={"email": "renji@example.com", "password": "wrong horse battery"},
    )
    unknown = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "wrong horse battery"},
    )

    assert valid.status_code == 200
    assert valid.json()["access_token"]
    assert invalid.status_code == unknown.status_code == 401
    assert invalid.json() == unknown.json()


def test_memory_routes_reject_missing_or_invalid_bearer_tokens(auth_client):
    client, _ = auth_client

    assert client.get("/memories").status_code == 401
    assert (
        client.get(
            "/memories", headers={"Authorization": "Bearer invalid-token"}
        ).status_code
        == 401
    )


def test_second_user_cannot_read_update_or_delete_first_users_memory(auth_client):
    client, _ = auth_client
    first = register(client).json()
    created = client.post(
        "/memories",
        headers={"Authorization": f"Bearer {first['access_token']}"},
        json={"title": "Private", "content": "account one"},
    ).json()
    second = register(
        client, email="second@example.com", password="another safe password"
    ).json()
    headers = {"Authorization": f"Bearer {second['access_token']}"}

    assert client.get("/memories", headers=headers).json() == []
    assert client.get(f"/memories/{created['id']}", headers=headers).status_code == 404
    assert (
        client.patch(
            f"/memories/{created['id']}",
            headers=headers,
            json={"title": "Stolen"},
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/memories/{created['id']}", headers=headers).status_code == 404
    )


def test_logout_revokes_session_and_expired_session_is_rejected(auth_client):
    client, test_session = auth_client
    signed_in = register(client).json()
    auth_header = {"Authorization": f"Bearer {signed_in['access_token']}"}
    assert client.get("/memories", headers=auth_header).status_code == 200

    assert client.post("/auth/logout", headers=auth_header).status_code == 204
    assert client.get("/memories", headers=auth_header).status_code == 401

    second = client.post(
        "/auth/login",
        json={"email": "renji@example.com", "password": "correct horse battery"},
    ).json()
    with test_session() as session:
        stored = session.get(
            UserSession, session.scalar(select(UserSession.token_hash))
        )
        assert stored is not None
        stored.expires_at = utc_now() - timedelta(seconds=1)
        session.commit()
    expired_header = {"Authorization": f"Bearer {second['access_token']}"}
    assert client.get("/memories", headers=expired_header).status_code == 401
