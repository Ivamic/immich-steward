# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health endpoint: application version and database status."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from steward import __version__
from steward.db import check_database

router = APIRouter()


class DatabaseHealth(BaseModel):
    ok: bool
    server_version: str | None
    pgvector_version: str | None
    # Machine-readable error class name; the UI maps it to a translated message.
    error: str | None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: DatabaseHealth


@router.get("/health")
async def health(request: Request) -> Health:
    db = await check_database(request.app.state.engine)
    return Health(
        status="ok" if db.ok and db.pgvector_version else "degraded",
        version=__version__,
        database=DatabaseHealth(
            ok=db.ok,
            server_version=db.server_version,
            pgvector_version=db.pgvector_version,
            error=db.error,
        ),
    )
