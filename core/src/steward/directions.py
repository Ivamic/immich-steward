# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which way the camera looked when a photo was taken (D-236, D-245), kept in the app.

Immich has no field for it, so it is never written there. Sources for now: a street-level image
the user put the point on (its heading as it is, wide); later the match of the photo with such
an image (narrow), the compass in the original file, by hand.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from steward.models import AssetDirection

Source = Literal["street", "street_match"]
SOURCES: tuple[str, ...] = ("street", "street_match")


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


async def forget(db: AsyncSession, asset_id: UUID) -> bool:
    """Drops the direction of the photo (not committed); False when it had none."""
    result = await db.execute(delete(AssetDirection).where(AssetDirection.asset_id == asset_id))
    return bool(result.rowcount)  # type: ignore[attr-defined]
