# SPDX-License-Identifier: AGPL-3.0-or-later
"""Database engine and connectivity checks."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

CONNECT_TIMEOUT_S = 3


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"timeout": CONNECT_TIMEOUT_S},
    )


@dataclass(frozen=True)
class DatabaseStatus:
    ok: bool
    server_version: str | None = None
    pgvector_version: str | None = None
    error: str | None = None


async def check_database(engine: AsyncEngine) -> DatabaseStatus:
    try:
        async with engine.connect() as conn:
            server_version = await conn.scalar(text("SHOW server_version"))
            pgvector_version = await conn.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
    except Exception as exc:
        return DatabaseStatus(ok=False, error=type(exc).__name__)
    return DatabaseStatus(ok=True, server_version=server_version, pgvector_version=pgvector_version)
