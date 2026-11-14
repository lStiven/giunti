"""`GET /api/v1/models`: the LLM models clients can choose from, grouped by provider.

Only enabled models are listed (their provider has an API key). Only what a client needs to
choose is exposed: never the provider's model names, limits or keys.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import LLMCatalog, Settings, get_settings
from app.core.errors import AppError, ErrorCode

router = APIRouter(prefix="/api/v1", tags=["models"])


class ModelInfo(BaseModel):
    id: str
    label: str
    description: str
    vision: bool
    free: bool
    is_default: bool


class ProviderModels(BaseModel):
    id: str
    label: str
    description: str
    models: list[ModelInfo]


class ModelCatalogResponse(BaseModel):
    default_model: str
    """Model id used when the request does not choose one."""

    providers: list[ProviderModels]


def catalog_response(catalog: LLMCatalog) -> ModelCatalogResponse:
    if not catalog.models:
        raise AppError(ErrorCode.NO_MODELS_AVAILABLE)
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
                    is_default=model.id == catalog.default_model,
                )
                for model in catalog.models
                if model.provider == provider_id
            ],
        )
        for provider_id, provider in catalog.providers.items()
    ]
    return ModelCatalogResponse(default_model=catalog.default_model, providers=providers)


@router.get("/models")
def list_models(settings: Annotated[Settings, Depends(get_settings)]) -> ModelCatalogResponse:
    return catalog_response(settings.enabled_llm_catalog())
