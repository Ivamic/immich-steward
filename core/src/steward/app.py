# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI application factory."""

import asyncio
import contextlib
import logging
import mimetypes
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx2
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from steward import __version__
from steward.api import assets, auth, health, library, maps, selection, worker
from steward.config import Settings, environment_warnings, get_settings
from steward.db import create_engine
from steward.deps import ImmichClientFactory
from steward.errors import ApiError, api_error_handler
from steward.immich import ImmichClient
from steward.immich.thumbnails import ThumbnailFetcher
from steward.jobs import JobRunner
from steward.worker_refusals import WorkerRefusals

log = logging.getLogger(__name__)

# Module workers (the map) are refused by browsers unless served with a JavaScript type;
# some systems do not know the .mjs extension.
mimetypes.add_type("text/javascript", ".mjs")


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


def create_app(
    settings: Settings | None = None,
    immich_factory: ImmichClientFactory = ImmichClient,
    immich_transport: httpx2.AsyncBaseTransport | None = None,
) -> FastAPI:
    """`immich_factory` and `immich_transport` let tests replace the real Immich server."""
    if settings is None:
        settings = get_settings()
        for warning in environment_warnings(os.environ):
            log.warning(warning)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(settings.database_url)
        app.state.sessionmaker = async_sessionmaker(app.state.engine, expire_on_commit=False)
        app.state.thumbnails = (
            ThumbnailFetcher(settings.immich_url, immich_transport) if settings.immich_url else None
        )
        app.state.job_runner = JobRunner(app.state.sessionmaker, settings, immich_factory)
        stop = asyncio.Event()
        runner_task = (
            asyncio.create_task(app.state.job_runner.run_forever(stop))
            if settings.run_jobs
            else None
        )
        try:
            yield
        finally:
            stop.set()
            if runner_task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await runner_task
            if app.state.thumbnails is not None:
                await app.state.thumbnails.aclose()
            await app.state.engine.dispose()

    app = FastAPI(title="immich-steward", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.worker_refusals = WorkerRefusals()
    app.state.immich_factory = immich_factory
    # Satellite map providers (key checks, usage); tests replace them with a fake.
    app.state.map_transport = None
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(library.router, prefix="/api")
    app.include_router(assets.router, prefix="/api")
    app.include_router(maps.router, prefix="/api")
    app.include_router(selection.router, prefix="/api")
    app.include_router(worker.router, prefix="/api")

    static_dir = settings.static_dir
    if static_dir is not None and Path(static_dir, "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="ui")

    return app
