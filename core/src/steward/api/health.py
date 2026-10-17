# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health endpoint: application version, database and Immich status."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from steward import __version__
from steward.db import check_database
from steward.deps import ImmichFactoryDep, SettingsDep
from steward.immich import ImmichError
from steward.immich.compat import is_supported

router = APIRouter()

# Keeps the endpoint fast when Immich does not answer: the Docker healthcheck gives it 4 s.
IMMICH_TIMEOUT_S = 2.0


class DatabaseHealth(BaseModel):
    ok: bool
    server_version: str | None
    pgvector_version: str | None
    # Machine-readable error class name; the UI maps it to a translated message.
    error: str | None


class ImmichHealth(BaseModel):
    configured: bool
    reachable: bool
    version: str | None
    supported: bool | None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: DatabaseHealth
    immich: ImmichHealth


async def check_immich(settings: SettingsDep, immich_factory: ImmichFactoryDep) -> ImmichHealth:
    if settings.immich_url is None:
        return ImmichHealth(configured=False, reachable=False, version=None, supported=None)
    try:
        async with asyncio.timeout(IMMICH_TIMEOUT_S):
            async with immich_factory(settings.immich_url, None) as client:
                version = await client.server_version()
    except (ImmichError, TimeoutError):
        return ImmichHealth(configured=True, reachable=False, version=None, supported=None)
    return ImmichHealth(
        configured=True, reachable=True, version=str(version), supported=is_supported(version)
    )


@router.get("/health")
async def health(
    request: Request, settings: SettingsDep, immich_factory: ImmichFactoryDep
) -> Health:
    db = await check_database(request.app.state.engine)
    immich = await check_immich(settings, immich_factory)
    healthy = db.ok and bool(db.pgvector_version) and immich.reachable and bool(immich.supported)
    return Health(
        status="ok" if healthy else "degraded",
        version=__version__,
        database=DatabaseHealth(
            ok=db.ok,
            server_version=db.server_version,
            pgvector_version=db.pgvector_version,
            error=db.error,
        ),
        immich=immich,
    )
