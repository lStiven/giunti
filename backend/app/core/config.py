"""Application settings loaded from environment variables (and `.env` in development)."""

from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMModelConfig(BaseModel):
    """One model of the fallback chain and its capabilities."""

    model: str = Field(description='LiteLLM model name: "provider/model"')
    vision: bool = True
    max_output_tokens: int = 32_000
    max_input_tokens: int | None = None


class ApiKeyEntry(BaseModel):
    """An authorized client. Only the HMAC hash of its key is stored."""

    id: str
    hash: str
    active: bool = True
    per_minute_limit: int = 10
    daily_limit: int = 100


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = []

    max_file_size_mb: int = 20
    max_pages: int = 60
    max_uncompressed_mb: int = 200

    libreoffice_path: str = "soffice"
    render_dpi: int = 150
    render_max_px: int = 1568

    llm_models: list[LLMModelConfig] = []
    llm_timeout_s: int = 300
    llm_max_retries: int = 2
    llm_repair_attempts: int = 1

    api_key_pepper: SecretStr = SecretStr("")
    api_keys: list[ApiKeyEntry] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
