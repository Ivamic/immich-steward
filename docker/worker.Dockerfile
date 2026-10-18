# SPDX-License-Identifier: AGPL-3.0-or-later
# Worker of immich-steward with the CPU build of PyTorch (for servers without a GPU).
# Models are downloaded on first use into /models; mount a volume there to keep them.

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.13.1

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/venv
WORKDIR /src
# Dependencies first: they change rarely and take most of the build time.
COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml core/
COPY worker/pyproject.toml worker/
RUN uv sync --frozen --no-dev --package steward-worker --extra geoclip --extra cpu \
    --no-install-workspace
COPY worker/ worker/
RUN uv sync --frozen --no-dev --package steward-worker --extra geoclip --extra cpu \
    --no-editable

FROM python:${PYTHON_VERSION}-slim
RUN useradd --system --uid 1000 --home-dir /app steward \
    && mkdir /models && chown steward /models
COPY --from=build /app/venv /app/venv
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
ENV PATH=/app/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    HF_HUB_DISABLE_PROGRESS_BARS=1
WORKDIR /app
USER steward
ENTRYPOINT ["steward-worker"]
