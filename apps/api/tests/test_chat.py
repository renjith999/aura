from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.routes.chat import get_openai_service
from app.main import app

client = TestClient(app)


def test_chat() -> None:
    openai_service = AsyncMock()
    openai_service.generate_response.return_value = "Hello from mocked OpenAI"
    app.dependency_overrides[get_openai_service] = lambda: openai_service

    try:
        response = client.post(
            "/chat",
            json={"message": "Hello Aura"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"response": "Hello from mocked OpenAI"}

    openai_service.generate_response.assert_awaited_once_with("Hello Aura")


def test_chat_openai_error() -> None:
    openai_service = AsyncMock()
    openai_service.generate_response.side_effect = Exception("OpenAI unavailable")
    app.dependency_overrides[get_openai_service] = lambda: openai_service

    try:
        response = client.post(
            "/chat",
            json={"message": "Hello Aura"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to generate an AI response."}
