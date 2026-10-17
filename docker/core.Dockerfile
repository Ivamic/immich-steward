# SPDX-License-Identifier: AGPL-3.0-or-later
# Core image: FastAPI service with the built web UI. Build from the repository root:
#   docker build -f docker/core.Dockerfile .

ARG NODE_VERSION=24
ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.13.1
ARG PNPM_VERSION=12.10.1

# --- Web UI -------------------------------------------------------------------
FROM node:${NODE_VERSION}-slim AS frontend
ARG PNPM_VERSION
RUN npm install --global pnpm@${PNPM_VERSION}
WORKDIR /src/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/.npmrc ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# --- Python dependencies ------------------------------------------------------
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS backend
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/venv
WORKDIR /src
# Dependencies first, so that code changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml core/
RUN uv sync --frozen --no-dev --package steward --no-install-workspace
COPY core/ core/
RUN uv sync --frozen --no-dev --package steward --no-editable

# --- Runtime ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim
RUN useradd --system --uid 1000 --home-dir /app steward
COPY --from=backend /app/venv /app/venv
COPY core/alembic.ini /app/alembic.ini
COPY core/migrations /app/migrations
COPY --from=frontend /src/frontend/build /app/static
COPY docker/core-entrypoint.sh /app/entrypoint.sh

ENV PATH=/app/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    STEWARD_STATIC_DIR=/app/static
WORKDIR /app
USER steward
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4)"]
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
