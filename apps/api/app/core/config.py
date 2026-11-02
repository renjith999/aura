from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    app_name: str = Field(default="Aura API", min_length=1, max_length=100)
    app_version: str = Field(default="0.1.0", min_length=1, max_length=40)
    environment: Literal["development", "test", "production"] = "development"
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    openai_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    database_url: SecretStr = Field(
        default=SecretStr("postgresql+psycopg://postgres:postgres@localhost:5432/aura"),
        repr=False,
    )
    access_token_ttl_seconds: int = Field(default=86400, gt=0, le=2_592_000)
    web_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    @field_validator("app_name", "app_version")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("web_origin")
    @classmethod
    def validate_web_origin(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            _ = parsed.port
        except ValueError:
            raise ValueError("WEB_ORIGIN must be a valid http(s) origin.") from None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("WEB_ORIGIN must be a valid http(s) origin.")
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        raw_url = value.get_secret_value().strip()
        if not raw_url or "://" not in raw_url:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy database URL.")
        try:
            make_url(raw_url)
        except (ArgumentError, ValueError):
            raise ValueError(
                "DATABASE_URL must be a valid SQLAlchemy database URL."
            ) from None
        return SecretStr(raw_url)

    @model_validator(mode="after")
    def validate_production_database(self) -> "Settings":
        if self.environment == "production":
            if "database_url" not in self.model_fields_set:
                raise ValueError(
                    "DATABASE_URL must be explicitly configured in production."
                )
            if make_url(self.database_url.get_secret_value()).drivername.startswith(
                "sqlite"
            ):
                raise ValueError("Production DATABASE_URL must use a server database.")
        return self


settings = Settings()
