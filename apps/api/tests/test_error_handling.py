import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import get_current_user_id
from app.core.database import get_db_session
from app.main import app
from app.models.base import Base


@pytest.fixture
def error_client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'errors.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_validation_and_not_found_errors_have_stable_shapes(error_client):
    invalid = error_client.post(
        "/memories?query=private-query-term",
        json={
            "title": " ",
            "content": "private note text that should not be echoed",
        },
    )

    assert invalid.status_code == 422
    assert invalid.json() == {
        "detail": "Request validation failed.",
        "code": "validation_error",
    }
    assert invalid.headers.get("X-Request-ID")
    assert "private note text" not in invalid.text

    missing = error_client.get("/memories/missing")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Memory not found.", "code": "not_found"}
    assert missing.headers.get("X-Request-ID")


def test_unexpected_errors_are_generic_and_logs_omit_private_content(
    error_client,
    caplog,
):
    private_content = "private memory content should never enter logs"

    def fail_session():
        raise RuntimeError(private_content)

    app.dependency_overrides[get_db_session] = fail_session
    caplog.set_level(logging.INFO, logger="aura.api")

    response = error_client.post(
        "/memories?query=private-query-term",
        headers={"Authorization": "Bearer private-access-token"},
        json={"title": "Private note", "content": private_content},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "An unexpected error occurred.",
        "code": "internal_error",
    }
    assert response.headers.get("X-Request-ID")
    assert "exception_type=RuntimeError" in caplog.text
    assert "method=POST" in caplog.text
    assert "status_code=500" in caplog.text
    assert response.headers["X-Request-ID"] in caplog.text
    assert "private-query-term" not in caplog.text
    assert "private-access-token" not in caplog.text
    assert private_content not in caplog.text
