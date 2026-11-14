import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.auth.dependencies import AuthenticatedClient, require_client
from app.auth.rate_limit import Quota
from app.core.config import (
    DEFAULT_CATALOG_FILE,
    LLMCatalog,
    Settings,
    get_settings,
    load_catalog,
)
from app.main import app

PROVIDERS: dict[str, Any] = {
    "gemini": {"label": "Google Gemini", "description": "Main provider."},
    "groq": {"label": "Groq", "description": "Free plan."},
}


def _model(model_id: str, model: str, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"id": model_id, "model": model, "label": model_id.title(), **extra}


CATALOG = LLMCatalog.model_validate(
    {
        "default_model": "flash",
        "providers": PROVIDERS,
        "models": [
            _model("flash", "gemini/flash", description="Fast."),
            _model("qwen", "groq/qwen", free=True, vision=False, description="Free."),
        ],
    }
)


def _settings(**keys: str) -> Settings:
    return Settings(
        llm_catalog=CATALOG,
        gemini_api_key=SecretStr(keys["gemini"]) if "gemini" in keys else None,
        llm_api_keys={
            provider: SecretStr(key) for provider, key in keys.items() if provider != "gemini"
        },
    )


def _get_models(settings: Settings) -> Any:  # noqa: ANN401 - raw JSON body
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_client] = lambda: AuthenticatedClient(
        id="test", quota=Quota(per_minute=100, daily=100)
    )
    try:
        response = TestClient(app).get("/api/v1/models")
    finally:
        app.dependency_overrides.clear()
    return response


def test_versioned_catalog_is_valid() -> None:
    catalog = load_catalog(DEFAULT_CATALOG_FILE)

    assert catalog.find(catalog.default_model) is not None
    assert all(model.label and model.description for model in catalog.models)
    assert all(provider.description for provider in catalog.providers.values())


def test_settings_load_the_catalog_file(tmp_path: Path) -> None:
    catalog_file = tmp_path / "catalog.toml"
    catalog_file.write_text(
        'default_model = "flash"\n\n[providers.gemini]\nlabel = "G"\ndescription = "d"\n\n'
        '[[models]]\nid = "flash"\nmodel = "gemini/flash"\n'
    )

    settings = Settings(llm_catalog_file=catalog_file)

    assert [model.id for model in settings.llm_catalog.models] == ["flash"]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"default_model": "x", "models": [_model("x", "gemini/a"), _model("x", "gemini/b")]},
            "Duplicated model ids: x",
        ),
        (
            {"default_model": "x", "models": [_model("x", "openai/gpt")]},
            "without a [providers.<id>] entry: openai",
        ),
        (
            {"default_model": "missing", "models": [_model("x", "gemini/a")]},
            "default_model 'missing' is not one of the catalog models",
        ),
        (
            {"default_model": "Not Valid", "models": [_model("Not Valid", "gemini/a")]},
            "String should match pattern",
        ),
    ],
)
def test_inconsistent_catalogs_are_rejected(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=re.escape(message)):
        LLMCatalog.model_validate({"providers": PROVIDERS, **data})


def test_unreadable_catalog_file_fails_with_its_path(tmp_path: Path) -> None:
    catalog_file = tmp_path / "broken.toml"
    catalog_file.write_text("[[models]\n")

    with pytest.raises(ValueError, match=r"broken\.toml"):
        load_catalog(catalog_file)


def test_only_models_whose_provider_has_a_key_are_enabled() -> None:
    enabled = _settings(groq="groq-key").enabled_llm_catalog()

    assert [model.id for model in enabled.models] == ["qwen"]
    assert list(enabled.providers) == ["groq"]
    assert enabled.default_model == "qwen"


@pytest.mark.parametrize("key", ["", "   "])
def test_empty_api_keys_count_as_missing(key: str) -> None:
    settings = _settings(gemini=key, groq=key)

    assert settings.llm_api_key("gemini") is None
    assert settings.enabled_llm_catalog().models == []


def test_gemini_key_can_come_from_either_variable() -> None:
    from_list = Settings(llm_catalog=CATALOG, llm_api_keys={"gemini": SecretStr("a")})
    from_own_variable = _settings(gemini="b")

    assert from_list.llm_api_key("gemini") == "a"
    assert from_own_variable.llm_api_key("gemini") == "b"


def test_models_endpoint_lists_enabled_models_by_provider_without_internal_details() -> None:
    response = _get_models(_settings(gemini="g-key", groq="groq-key"))

    assert response.status_code == 200
    assert response.json() == {
        "default_model": "flash",
        "providers": [
            {
                "id": "gemini",
                "label": "Google Gemini",
                "description": "Main provider.",
                "models": [
                    {
                        "id": "flash",
                        "label": "Flash",
                        "description": "Fast.",
                        "vision": True,
                        "free": False,
                        "is_default": True,
                    }
                ],
            },
            {
                "id": "groq",
                "label": "Groq",
                "description": "Free plan.",
                "models": [
                    {
                        "id": "qwen",
                        "label": "Qwen",
                        "description": "Free.",
                        "vision": False,
                        "free": True,
                        "is_default": False,
                    }
                ],
            },
        ],
    }


def test_models_endpoint_hides_models_without_api_key() -> None:
    response = _get_models(_settings(gemini="g-key"))

    providers = response.json()["providers"]
    assert [provider["id"] for provider in providers] == ["gemini"]


def test_models_endpoint_without_any_api_key_explains_the_problem() -> None:
    response = _get_models(_settings())

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "NO_MODELS_AVAILABLE"
    assert "API key" in error["message"]
