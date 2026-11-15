"""`GET /api/v1/models`: the LLM models clients can choose from, grouped by provider.

Only enabled models are listed (their provider has an API key). Only what a client needs to
choose is exposed: never the provider's model names, limits or keys.
"""

from collections.abc import Collection
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import AuthenticatedClient, require_client
from app.core.config import LLMCatalog, ReasoningMode, Settings, get_settings
from app.core.errors import AppError, ErrorCode

router = APIRouter(prefix="/api/v1", tags=["models"])


class ModelInfo(BaseModel):
    id: str
    label: str
    description: str
    vision: bool
    free: bool
    is_default: bool
    modes: list[ReasoningMode]
    """Reasoning modes the model offers: always "precise", and "fast" when configured."""


class ProviderModels(BaseModel):
    id: str
    label: str
    description: str
    models: list[ModelInfo]


class ModelCatalogResponse(BaseModel):
    default_model: str
    """Model id used when the request does not choose one."""

    default_mode: ReasoningMode
    """Mode used when the request does not choose one (precise for models without fast)."""

    providers: list[ProviderModels]


def catalog_response(
    catalog: LLMCatalog, allowed_modes: Collection[ReasoningMode] = ("fast", "precise")
) -> ModelCatalogResponse:
    """The catalog as one client sees it: only the modes it may use, and the models offering one."""
    if not catalog.models:
        raise AppError(ErrorCode.NO_MODELS_AVAILABLE)
    usable = {
        model.id: [mode for mode in model.modes if mode in allowed_modes]
        for model in catalog.models
    }
    models = [model for model in catalog.models if usable[model.id]]
    if not models:
        raise AppError(ErrorCode.NO_MODELS_AVAILABLE)
    default_model = catalog.default_model if usable.get(catalog.default_model) else models[0].id
    default_mode = catalog.default_mode if catalog.default_mode in allowed_modes else "fast"
    providers = [
        ProviderModels(
            id=provider_id,
            label=provider.label,
            description=provider.description,
            models=[
                ModelInfo(
                    id=model.id,
                    label=model.label or model.id,
                    description=model.description,
                    vision=model.vision,
                    free=model.free,
                    is_default=model.id == default_model,
                    modes=usable[model.id],
                )
                for model in models
                if model.provider == provider_id
            ],
        )
        for provider_id, provider in catalog.providers.items()
        if any(model.provider == provider_id for model in models)
    ]
    return ModelCatalogResponse(
        default_model=default_model, default_mode=default_mode, providers=providers
    )


@router.get("/models")
def list_models(
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[AuthenticatedClient, Depends(require_client)],
) -> ModelCatalogResponse:
    return catalog_response(settings.enabled_llm_catalog(), client.allowed_modes)
