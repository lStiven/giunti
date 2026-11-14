# Development image only; production images are backend/Dockerfile and frontend/Dockerfile.
# Keep Debian (bookworm), Python (3.13), Node (22) and uv (0.12.5) aligned with those images.
FROM mcr.microsoft.com/devcontainers/python:1-3.13-bookworm

# The base image ships a Yarn apt source whose signing key is no longer valid; Yarn is unused.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui \
        fonts-dejavu-core \
        fonts-liberation2 \
        jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /usr/local/bin/

USER vscode
ENV PATH="/home/vscode/.local/bin:${PATH}" \
    UV_LINK_MODE=copy
RUN uv tool install rust-just==1.58.0 \
    && uv tool install pre-commit==4.0.1
