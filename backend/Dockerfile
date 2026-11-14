# Keep Debian (bookworm), Python (3.13) and uv (0.12.5) aligned with .devcontainer/Dockerfile.
FROM python:3.13-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui \
        fonts-dejavu-core \
        fonts-liberation2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY llm_catalog.toml ./
COPY app ./app

RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown appuser /app/data
USER appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
