"""Application settings loaded from environment variables (and `.env` in development).

The LLM model catalog is a versioned TOML file (`llm_catalog.toml`); API keys stay in the
environment.
"""

import tomllib
from collections.abc import Collection
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

type ReasoningEffort = Literal["minimal", "low", "medium", "high"]

DEFAULT_CATALOG_FILE = Path(__file__).resolve().parents[2] / "llm_catalog.toml"


class ProviderInfo(BaseModel):
    label: str
    description: str


class LLMModelConfig(BaseModel):
    """One model of the catalog and its capabilities."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,63}$")
    model: str = Field(description='LiteLLM model name: "provider/model"')
    label: str = ""
    description: str = ""
    free: bool = False
    vision: bool = True
    max_output_tokens: int = 32_000
    max_input_tokens: int | None = Field(
        default=None, description="Context window; looked up in LiteLLM when not set"
    )
    temperature: float | None = Field(
        default=None, description="None keeps the provider default (recommended for Gemini 3)"
    )
    reasoning_effort: ReasoningEffort | None = None
    json_mode: bool = Field(
        default=True, description="Ask the provider for JSON-only output when it supports it"
    )

    @property
    def provider(self) -> str:
        return self.model.split("/", 1)[0]


class LLMCatalog(BaseModel):
    """Models clients can choose from. There is no fallback: each request uses one model."""

    default_model: str = ""
    providers: dict[str, ProviderInfo] = {}
    models: list[LLMModelConfig] = []

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        ids = [model.id for model in self.models]
        duplicated = sorted({model_id for model_id in ids if ids.count(model_id) > 1})
        if duplicated:
            message = f"Duplicated model ids: {', '.join(duplicated)}"
            raise ValueError(message)
        unknown = sorted({m.provider for m in self.models if m.provider not in self.providers})
        if unknown:
            message = f"Models use providers without a [providers.<id>] entry: {', '.join(unknown)}"
            raise ValueError(message)
        if self.models and self.find(self.default_model) is None:
            message = f"default_model '{self.default_model}' is not one of the catalog models"
            raise ValueError(message)
        return self

    def find(self, model_id: str) -> LLMModelConfig | None:
        return next((model for model in self.models if model.id == model_id), None)

    def enabled(self, providers_with_key: Collection[str]) -> "LLMCatalog":
        """The models whose provider has an API key. The default falls back to the first one."""
        models = [model for model in self.models if model.provider in providers_with_key]
        providers = {
            provider_id: info
            for provider_id, info in self.providers.items()
            if any(model.provider == provider_id for model in models)
        }
        enabled_ids = {model.id for model in models}
        default_model = (
            self.default_model
            if self.default_model in enabled_ids
            else (models[0].id if models else "")
        )
        return LLMCatalog(default_model=default_model, providers=providers, models=models)


def load_catalog(path: Path) -> LLMCatalog:
    try:
        with path.open("rb") as file:
            return LLMCatalog.model_validate(tomllib.load(file))
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
        message = f"Invalid LLM catalog {path}: {exc}"
        raise ValueError(message) from exc


CLIENT_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,31}$"
MIN_PEPPER_LENGTH = 32
PEPPER_PLACEHOLDER_PREFIX = "change-me"


class ApiKeyEntry(BaseModel):
    """An authorized client. Only the HMAC hash of its key is stored."""

    id: str = Field(pattern=CLIENT_ID_PATTERN)
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    active: bool = True
    per_minute_limit: int = Field(default=10, ge=1)
    daily_limit: int = Field(default=100, ge=1)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = []

    max_file_size_mb: int = 20
    max_pages: int = 60
    max_uncompressed_mb: int = 200

    libreoffice_path: str = "soffice"
    libreoffice_timeout_s: int = 120
    render_dpi: int = 150
    render_max_px: int = 1568

    llm_catalog_file: Path = DEFAULT_CATALOG_FILE
    llm_catalog: LLMCatalog = Field(
        default_factory=LLMCatalog, description="Loaded from llm_catalog_file when not given"
    )
    llm_timeout_s: int = 300
    llm_max_retries: int = 2
    llm_repair_attempts: int = 1
    gemini_api_key: SecretStr | None = None
    llm_api_keys: dict[str, SecretStr] = Field(
        default={}, description='Keys of the other providers: {"<provider>": "<key>"}'
    )

    api_key_pepper: SecretStr = SecretStr("")
    api_keys: list[ApiKeyEntry] = []

    @model_validator(mode="after")
    def _load_catalog(self) -> Self:
        if not self.llm_catalog.models and self.llm_catalog_file.is_file():
            self.llm_catalog = load_catalog(self.llm_catalog_file)
        return self

    @model_validator(mode="after")
    def _check_api_keys(self) -> Self:
        ids = [entry.id for entry in self.api_keys]
        duplicated = sorted({client for client in ids if ids.count(client) > 1})
        if duplicated:
            message = f"API_KEYS has duplicated client ids: {', '.join(duplicated)}"
            raise ValueError(message)
        if self.app_env == "production" and not self.has_secure_pepper():
            message = (
                f"API_KEY_PEPPER must be a random secret of at least {MIN_PEPPER_LENGTH} "
                "characters in production"
            )
            raise ValueError(message)
        return self

    def has_secure_pepper(self) -> bool:
        pepper = self.api_key_pepper.get_secret_value()
        return len(pepper) >= MIN_PEPPER_LENGTH and not pepper.startswith(PEPPER_PLACEHOLDER_PREFIX)

    def llm_api_key(self, provider: str) -> str | None:
        """The provider's API key, or None when it is missing or empty."""
        key = self.llm_api_keys.get(provider)
        if key is None and provider == "gemini":
            key = self.gemini_api_key
        value = key.get_secret_value().strip() if key is not None else ""
        return value or None

    def llm_api_keys_by_provider(self) -> dict[str, str]:
        providers = {model.provider for model in self.llm_catalog.models}
        return {
            provider: key
            for provider in sorted(providers)
            if (key := self.llm_api_key(provider)) is not None
        }

    def enabled_llm_catalog(self) -> LLMCatalog:
        """Only the models whose provider has an API key can be used."""
        return self.llm_catalog.enabled(self.llm_api_keys_by_provider().keys())


@lru_cache
def get_settings() -> Settings:
    return Settings()
