# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from steward import __version__
from steward.api import health
from steward.config import Settings, get_settings
from steward.db import create_engine


class SPAStaticFiles(StaticFiles):
    """Serves the built web UI; unknown paths fall back to index.html (client-side routing)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # Unknown API paths must stay real 404s, not the UI page.
            # `path` is OS-normalized (backslashes on Windows).
            first_segment = path.replace("\\", "/").split("/", 1)[0]
            if exc.status_code != 404 or first_segment == "api":
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(settings.database_url)
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="immich-steward", version=__version__, lifespan=lifespan)
    app.include_router(health.router, prefix="/api")

    static_dir = settings.static_dir
    if static_dir is not None and Path(static_dir, "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="ui")

    return app
