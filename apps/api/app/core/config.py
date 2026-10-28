from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Aura API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_port: int = 8000

    openai_api_key: str = ""
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/aura"
    access_token_ttl_seconds: int = Field(default=86400, gt=0, le=2_592_000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
