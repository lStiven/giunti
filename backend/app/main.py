"""API entry point."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Questionnaire extraction",
        version="0.1.0",
        description="Turns questionnaires and tests (PDF, DOCX, XLSX) into structured JSON.",
    )
    app.include_router(health_router)
    return app


app = create_app()
