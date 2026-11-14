"""API entry point."""

from fastapi import FastAPI

from app.api.error_handlers import ErrorResponse, register_error_handlers
from app.api.health import router as health_router
from app.api.llm_models import router as llm_models_router
from app.api.middleware import RequestContextMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.extraction.routes import router as questionnaires_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Questionnaire extraction",
        version="0.1.0",
        description="Turns questionnaires and tests (PDF, DOCX, XLSX) into structured JSON.",
        responses={"default": {"model": ErrorResponse, "description": "Error"}},
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(llm_models_router)
    app.include_router(questionnaires_router)
    return app


app = create_app()
