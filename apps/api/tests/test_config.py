from app.core.config import settings


def test_app_configuration() -> None:
    assert settings.app_name == "Aura API"
    assert settings.app_version == "0.1.0"
    assert settings.environment == "development"
    assert settings.api_port == 8000
