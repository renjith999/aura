from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.routes.chat import get_openai_service, settings
from app.main import app


def _authorized_headers(
    client: TestClient, email: str = "chat@example.com"
) -> dict[str, str]:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery"},
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_chat_requires_authentication(auth_client) -> None:
    client, _ = auth_client

    response = client.post("/chat", json={"message": "Hello Aura"})

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Authentication is required.",
        "code": "unauthorized",
    }
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_chat_uses_authenticated_user_and_calls_provider(
    auth_client, monkeypatch
) -> None:
    client, _ = auth_client
    headers = _authorized_headers(client)
    openai_service = AsyncMock()
    openai_service.generate_response.return_value = "Hello from mocked OpenAI"
    monkeypatch.setitem(
        app.dependency_overrides, get_openai_service, lambda: openai_service
    )

    response = client.post("/chat", headers=headers, json={"message": "Hello Aura"})

    assert response.status_code == 200
    assert response.json() == {"response": "Hello from mocked OpenAI"}
    openai_service.generate_response.assert_awaited_once_with("Hello Aura")


def test_chat_rate_limit_is_per_user_and_returns_retry_after(
    auth_client, monkeypatch
) -> None:
    client, _ = auth_client
    first_user = _authorized_headers(client, "first@example.com")
    second_user = _authorized_headers(client, "second@example.com")
    openai_service = AsyncMock()
    openai_service.generate_response.return_value = "A response"
    window_start = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    monkeypatch.setattr("app.api.routes.chat.utc_now", lambda: window_start)
    monkeypatch.setattr(settings, "chat_rate_limit_per_minute", 1)
    monkeypatch.setitem(
        app.dependency_overrides, get_openai_service, lambda: openai_service
    )

    first_request = client.post(
        "/chat", headers=first_user, json={"message": "First request"}
    )
    limited_request = client.post(
        "/chat", headers=first_user, json={"message": "Second request"}
    )
    other_user_request = client.post(
        "/chat", headers=second_user, json={"message": "Their first request"}
    )

    assert first_request.status_code == 200
    assert limited_request.status_code == 429
    assert limited_request.json() == {
        "detail": "Chat usage limit reached. Try again later.",
        "code": "rate_limited",
    }
    assert 1 <= int(limited_request.headers["Retry-After"]) <= 60
    assert other_user_request.status_code == 200

    monkeypatch.setattr(
        "app.api.routes.chat.utc_now",
        lambda: window_start + timedelta(seconds=61),
    )
    after_window_request = client.post(
        "/chat", headers=first_user, json={"message": "Window reset"}
    )

    assert after_window_request.status_code == 200
    assert openai_service.generate_response.await_count == 3


def test_chat_rejects_messages_over_the_configured_length(
    auth_client, monkeypatch
) -> None:
    client, _ = auth_client
    headers = _authorized_headers(client)
    openai_service = AsyncMock()
    monkeypatch.setitem(
        app.dependency_overrides, get_openai_service, lambda: openai_service
    )

    response = client.post(
        "/chat",
        headers=headers,
        json={"message": "a" * (settings.chat_max_input_characters + 1)},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    openai_service.generate_response.assert_not_awaited()


def test_chat_is_unavailable_without_api_key(auth_client, monkeypatch) -> None:
    client, _ = auth_client
    headers = _authorized_headers(client)
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))

    response = client.post("/chat", headers=headers, json={"message": "Hello Aura"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Chat is not configured.",
        "code": "unavailable",
    }


def test_chat_openapi_documents_auth_and_message_limit() -> None:
    openapi = app.openapi()
    operation = openapi["paths"]["/chat"]["post"]
    request_schema_ref = operation["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    schema_name = request_schema_ref.rsplit("/", maxsplit=1)[-1]
    message_schema = openapi["components"]["schemas"][schema_name]["properties"][
        "message"
    ]
    rate_limit_response = operation["responses"]["429"]

    assert operation["security"]
    assert message_schema["maxLength"] == settings.chat_max_input_characters
    assert rate_limit_response["headers"]["Retry-After"]["schema"]["type"] == "integer"
