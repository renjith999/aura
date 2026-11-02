import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings


def test_app_configuration() -> None:
    assert settings.app_name == "Aura API"
    assert settings.app_version == "0.1.0"
    assert settings.environment == "development"
    assert settings.api_port == 8000
    assert settings.log_level == "INFO"


def test_settings_load_values_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Configured Aura")
    monkeypatch.setenv("API_PORT", "8011")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./configured.db")
    monkeypatch.setenv("LOG_LEVEL", "warning")

    configured = Settings(_env_file=None)

    assert configured.app_name == "Configured Aura"
    assert configured.api_port == 8011
    assert configured.database_url.get_secret_value() == "sqlite:///./configured.db"
    assert configured.log_level == "WARNING"


@pytest.mark.parametrize(
    "values",
    [
        {"api_port": 0},
        {"api_port": 65536},
        {"web_origin": "localhost:5173"},
        {"web_origin": "http://localhost:99999"},
        {"database_url": "this is not a database url"},
    ],
)
def test_settings_reject_invalid_values(values) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_production_requires_explicit_server_database_url() -> None:
    with pytest.raises(
        ValidationError, match="DATABASE_URL must be explicitly configured"
    ):
        Settings(_env_file=None, environment="production")

    with pytest.raises(ValidationError, match="must use a server database"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="sqlite:///./aura.db",
        )


def test_secret_settings_are_redacted_from_repr() -> None:
    configured = Settings(
        _env_file=None,
        openai_api_key="test-openai-secret",
        database_url="postgresql+psycopg://user:database-secret@localhost/aura",
    )

    assert "test-openai-secret" not in repr(configured)
    assert "database-secret" not in repr(configured)


def test_api_runner_uses_configured_port(monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import patch

    from app import __main__ as api_runner

    monkeypatch.setattr(
        api_runner,
        "settings",
        SimpleNamespace(api_port=8012, environment="test"),
    )
    with patch.object(api_runner.uvicorn, "run") as run_server:
        api_runner.run()

    run_server.assert_called_once_with(
        "app.main:app",
        host="127.0.0.1",
        port=8012,
        reload=False,
    )


def test_api_runner_binds_production_interface(monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import patch

    from app import __main__ as api_runner

    monkeypatch.setattr(
        api_runner,
        "settings",
        SimpleNamespace(api_port=8000, environment="production"),
    )
    with patch.object(api_runner.uvicorn, "run") as run_server:
        api_runner.run()

    run_server.assert_called_once_with(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
