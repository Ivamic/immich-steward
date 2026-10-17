# SPDX-License-Identifier: AGPL-3.0-or-later
"""Writing locations to Immich, with history and undo (FR-50, FR-51, FR-52).

Only called from API requests made by the user; no module or background job writes to Immich
(FR-53).

Immich 3.3 has no way to clear coordinates (null is rejected), but its metadata job treats exactly
(0, 0) as "no GPS" and removes it within a second. Undoing a write over an empty location relies
on that and checks the result: if (0, 0) stays, our coordinates are put back.
"""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.errors import ApiError
from steward.immich import ImmichClient, ImmichError
from steward.models import Asset, LocationChange

# Coordinates read back from Immich are compared with this tolerance (about 1 cm).
SAME_POINT_DEGREES = 1e-7

HISTORY_LIMIT = 20

# Waiting for Immich to drop (0, 0) after an undo: up to 10 s.
CLEAR_POLL_S = 0.5
CLEAR_ATTEMPTS = 20

log = logging.getLogger(__name__)


async def write_location(
    db: AsyncSession,
    client: ImmichClient,
    asset: Asset,
    latitude: float,
    longitude: float,
    *,
    source: str,
    tag: str,
) -> LocationChange:
    """Writes the location to Immich and records the change; `tag` may be empty."""
    if is_null_island(latitude, longitude):
        # Immich would take it for "no location" and clear it.
        raise ApiError(422, "location_null_island")
    exif = (await client.asset(asset.immich_id)).exif_info
    prev_latitude = exif.latitude if exif else None
    prev_longitude = exif.longitude if exif else None
    await client.set_location(asset.immich_id, latitude, longitude)
    # The coordinates are already in Immich: a tagging failure must not lose the history.
    tag_added = bool(tag) and await _change_tag(client, tag, asset.immich_id, add=True)

    change = LocationChange(
        asset_id=asset.id,
        prev_latitude=prev_latitude,
        prev_longitude=prev_longitude,
        latitude=latitude,
        longitude=longitude,
        source=source,
        tag_added=tag_added,
        status="applied",
    )
    db.add(change)
    _set_local_location(asset, latitude, longitude)
    # A located photo is no longer skipped or "not applicable".
    asset.review_status = "new"
    await db.commit()
    return change


async def undo_last(db: AsyncSession, client: ImmichClient, asset: Asset, *, tag: str) -> None:
    """Restores the coordinates the last applied change replaced."""
    change = await db.scalar(
        select(LocationChange)
        .where(LocationChange.asset_id == asset.id, LocationChange.status == "applied")
        .order_by(LocationChange.created_at.desc())
        .limit(1)
    )
    if change is None:
        raise ApiError(409, "location_nothing_to_undo")

    exif = (await client.asset(asset.immich_id)).exif_info
    if not (
        exif and _same(exif.latitude, change.latitude) and _same(exif.longitude, change.longitude)
    ):
        # Someone changed the location after us; never overwrite it.
        raise ApiError(409, "location_changed_in_immich")

    if change.prev_latitude is None or change.prev_longitude is None:
        await _clear_location(client, asset, change)
    else:
        await client.set_location(asset.immich_id, change.prev_latitude, change.prev_longitude)
    if tag and change.tag_added:
        await _change_tag(client, tag, asset.immich_id, add=False)

    change.status = "undone"
    change.undone_at = datetime.now(UTC)
    _set_local_location(asset, change.prev_latitude, change.prev_longitude)
    await db.commit()


async def history(db: AsyncSession, asset: Asset) -> list[LocationChange]:
    return list(
        await db.scalars(
            select(LocationChange)
            .where(LocationChange.asset_id == asset.id)
            .order_by(LocationChange.created_at.desc())
            .limit(HISTORY_LIMIT)
        )
    )


def is_null_island(latitude: float, longitude: float) -> bool:
    return latitude == 0 and longitude == 0


async def _clear_location(client: ImmichClient, asset: Asset, change: LocationChange) -> None:
    await client.set_location(asset.immich_id, 0.0, 0.0)
    for _ in range(CLEAR_ATTEMPTS):
        await asyncio.sleep(CLEAR_POLL_S)
        exif = (await client.asset(asset.immich_id)).exif_info
        if exif is None or exif.latitude is None or exif.longitude is None:
            return
    # Immich kept (0, 0): never leave the photo there, restore what the user had picked.
    await client.set_location(asset.immich_id, change.latitude, change.longitude)
    raise ApiError(502, "location_clear_failed")


async def _change_tag(client: ImmichClient, tag: str, asset_id: UUID, *, add: bool) -> bool:
    try:
        tag_id = await client.upsert_tag(tag)
        if add:
            return await client.tag_asset(tag_id, asset_id)
        return await client.untag_asset(tag_id, asset_id)
    except ImmichError as exc:
        log.warning(
            "Could not %s tag %r on asset %s: %s", "add" if add else "remove", tag, asset_id, exc
        )
        return False


def _set_local_location(asset: Asset, latitude: float | None, longitude: float | None) -> None:
    asset.latitude = latitude
    asset.longitude = longitude
    # Immich recomputes the place name in the background; the next sync brings it in.
    asset.city = asset.state = asset.country = None


def _same(a: float | None, b: float) -> bool:
    return a is not None and abs(a - b) < SAME_POINT_DEGREES
