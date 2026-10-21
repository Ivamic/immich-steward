# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vectors of photos for the similar-photos module (M3, D-105).

Workers compute the vectors; the core keeps one per photo and module (the newest run replaces the
older vector) and one for the latest part of the photo. The search looks among the vectors of the
user's own photos that have a location (`Embedding.located`, kept in step with the assets here).
"""

import base64
import binascii
import math
import struct
from uuid import UUID

from sqlalchemy import and_, delete, func, not_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from steward.models import Account, Asset, Embedding, ModuleRun


class InvalidEmbedding(ValueError):
    pass


def located() -> ColumnElement[bool]:
    """Assets whose location can be suggested to other photos."""
    return and_(
        Asset.latitude.is_not(None),
        Asset.longitude.is_not(None),
        # Immich takes exactly (0, 0) for "no location".
        not_(and_(Asset.latitude == 0, Asset.longitude == 0)),
        Asset.is_trashed.is_(False),
    )


def is_located(asset: Asset) -> bool:
    """`located()` for an asset already loaded."""
    return (
        asset.latitude is not None
        and asset.longitude is not None
        and not (asset.latitude == 0 and asset.longitude == 0)
        and not asset.is_trashed
    )


def decode(data: str, dim: int) -> list[float]:
    """The vector a worker sent: base64 of `dim` little-endian float16 numbers."""
    try:
        raw = base64.b64decode(data, validate=True)
    except binascii.Error as exc:
        raise InvalidEmbedding("not base64") from exc
    if len(raw) != dim * 2:
        raise InvalidEmbedding(f"{len(raw)} bytes instead of {dim * 2}")
    values = list(struct.unpack(f"<{dim}e", raw))
    if not all(math.isfinite(v) for v in values):
        raise InvalidEmbedding("not finite")
    return values


async def store(
    db: AsyncSession, run: ModuleRun, asset: Asset, module_version: str, vector: list[float]
) -> None:
    """Keeps the vector of the run in place of the older one of the photo (or of its part)."""
    region = run.region is not None
    await db.execute(
        delete(Embedding).where(
            Embedding.asset_id == asset.id,
            Embedding.module_id == run.module_id,
            Embedding.region.is_(region),
        )
    )
    db.add(
        Embedding(
            run_id=run.id,
            asset_id=asset.id,
            account_id=asset.account_id,
            module_id=run.module_id,
            module_version=module_version,
            region=region,
            located=not region and is_located(asset),
            vector=vector,
        )
    )


async def index_counts(db: AsyncSession, account: Account, module_id: str) -> dict[str, int]:
    """How much of the search index is there: of the photos with a location that automatic runs
    index (`worker_queue.auto_enqueue`), how many have their vector."""
    photos = (
        Asset.account_id == account.id,
        Asset.type == "IMAGE",
        Asset.visibility.in_(("timeline", "archive")),
        located(),
    )
    located_photos = await db.scalar(select(func.count()).where(*photos))
    indexed = await db.scalar(
        select(func.count())
        .select_from(Embedding)
        .join(Asset, Asset.id == Embedding.asset_id)
        .where(*photos, Embedding.module_id == module_id, Embedding.located.is_(True))
    )
    return {"indexed": indexed or 0, "located": located_photos or 0}


async def refresh_located(
    db: AsyncSession, *, account_id: UUID | None = None, asset_id: UUID | None = None
) -> None:
    """Brings `Embedding.located` in line with the locations of the assets (after a sync, a
    written or undone location)."""
    statement = (
        update(Embedding)
        .where(
            Embedding.asset_id == Asset.id,
            Embedding.region.is_(False),
            Embedding.located.is_distinct_from(located()),
        )
        .values(located=located())
        .execution_options(synchronize_session=False)
    )
    if account_id is not None:
        statement = statement.where(Embedding.account_id == account_id)
    if asset_id is not None:
        statement = statement.where(Embedding.asset_id == asset_id)
    await db.execute(statement)
