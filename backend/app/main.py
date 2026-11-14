"""API entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import ErrorResponse, register_error_handlers
from app.api.health import router as health_router
from app.api.llm_models import router as llm_models_router
from app.api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.auth.admin_routes import router as admin_router
from app.auth.dependencies import API_KEY_HEADER
from app.auth.models import create_tables
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.logging import configure_logging
from app.extraction.routes import router as questionnaires_router

# Response headers the browser frontend reads; CORS hides them unless they are exposed.
EXPOSED_HEADERS = [
    REQUEST_ID_HEADER,
    "Retry-After",
    "X-RateLimit-Limit-Day",
    "X-RateLimit-Remaining-Day",
    "X-LLM-Model",
    "X-LLM-Input-Tokens",
    "X-LLM-Output-Tokens",
    "X-LLM-Repairs",
    "X-LLM-Duration-Ms",
    "X-Extraction-Parts",
    "X-Extraction-Warnings",
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_tables(get_engine())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Questionnaire extraction",
        version="0.1.0",
        description="Turns questionnaires and tests (PDF, DOCX, XLSX) into structured JSON.",
        responses={"default": {"model": ErrorResponse, "description": "Error"}},
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        # Added last so it wraps everything else and error responses also carry CORS headers.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=[API_KEY_HEADER, REQUEST_ID_HEADER, "Content-Type"],
            expose_headers=EXPOSED_HEADERS,
            max_age=600,
        )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(llm_models_router)
    app.include_router(questionnaires_router)
    app.include_router(admin_router)
    return app


app = create_app()
