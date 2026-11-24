# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which way the camera looked when a photo was taken (D-236, D-245), kept in the app.

Immich has no field for it, so it is never written there. Sources for now: a street-level image
the user put the point on (its heading as it is, wide); later the match of the photo with such
an image (narrow), the compass in the original file, by hand.
"""

import math
from collections.abc import Collection
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from steward.models import AssetDirection

Source = Literal["street", "street_match"]
SOURCES: tuple[str, ...] = ("street", "street_match")

# A place moved further than this is another place: the direction found at the old one is
# dropped. Nearer, the camera still looked the same way (D-246); as far as the strip of
# street-level images reaches.
MOVED_FAR_M = 100.0


def moved_far(
    old_lat: float | None, old_lon: float | None, lat: float | None, lon: float | None
) -> bool:
    """Whether a photo moved from one place to another far from it; from or to no place: no."""
    if old_lat is None or old_lon is None or lat is None or lon is None:
        return False
    rad = math.pi / 180
    h = (
        math.sin((lat - old_lat) * rad / 2) ** 2
        + math.cos(old_lat * rad) * math.cos(lat * rad) * math.sin((lon - old_lon) * rad / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(min(1.0, math.sqrt(h))) > MOVED_FAR_M


async def get(db: AsyncSession, asset_id: UUID) -> AssetDirection | None:
    return await db.get(AssetDirection, asset_id)


async def keep(
    db: AsyncSession,
    asset_id: UUID,
    heading: float,
    accuracy: float,
    source: str,
    source_ref: str | None,
) -> AssetDirection:
    """Keeps the direction of the photo, in place of the one it had (not committed)."""
    found = await db.get(AssetDirection, asset_id)
    if found is None:
        found = AssetDirection(asset_id=asset_id)
        db.add(found)
    found.heading = heading % 360
    found.accuracy = accuracy
    found.source = source
    found.source_ref = source_ref
    found.created_at = datetime.now(UTC)
    return found


async def forget_many(db: AsyncSession, asset_ids: Collection[UUID]) -> None:
    """Drops the directions of the photos (not committed)."""
    if asset_ids:
        await db.execute(delete(AssetDirection).where(AssetDirection.asset_id.in_(asset_ids)))


async def forget(db: AsyncSession, asset_id: UUID) -> bool:
    """Drops the direction of the photo (not committed); False when it had none."""
    result = await db.execute(delete(AssetDirection).where(AssetDirection.asset_id == asset_id))
    return bool(result.rowcount)  # type: ignore[attr-defined]
