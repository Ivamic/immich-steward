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
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward import embeddings
from steward.errors import ApiError
from steward.immich import ImmichClient, ImmichError
from steward.immich.models import ImmichAsset
from steward.models import Asset, LocationChange

# Coordinates read back from Immich are compared with this tolerance (about 1 cm).
SAME_POINT_DEGREES = 1e-7

HISTORY_LIMIT = 20

# Waiting for Immich to drop (0, 0) after an undo: up to 10 s.
CLEAR_POLL_S = 0.5
CLEAR_ATTEMPTS = 20

# Requests to Immich at a time when many photos are read or written.
CONCURRENCY = 8

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
    await embeddings.refresh_located(db, asset_id=asset.id)
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
    await embeddings.refresh_located(db, asset_id=asset.id)
    await db.commit()


@dataclass
class BatchResult:
    batch_id: UUID | None
    written: int = 0
    # Left as they were: they had a location and overwriting was not asked for.
    skipped_located: int = 0


async def write_batch(
    db: AsyncSession,
    client: ImmichClient,
    assets: list[Asset],
    latitude: float,
    longitude: float,
    *,
    overwrite: bool,
    tag: str,
) -> BatchResult:
    """Writes one location to several photos; the changes share a batch, undone together.

    Photos that already have a location (in Immich, read now) are left alone unless `overwrite`.
    """
    if is_null_island(latitude, longitude):
        raise ApiError(422, "location_null_island")
    current = await _read_all(client, assets)
    targets = [a for a in assets if overwrite or not _has_location(current[a.immich_id])]
    result = BatchResult(batch_id=None, skipped_located=len(assets) - len(targets))
    if not targets:
        return result
    await client.set_locations([a.immich_id for a in targets], latitude, longitude)
    # The coordinates are already in Immich: a tagging failure must not lose the history.
    tagged: set[UUID] = set()
    if tag:
        tagged = await _change_tags(client, tag, [a.immich_id for a in targets], add=True)

    result.batch_id = uuid.uuid4()
    for asset in targets:
        exif = current[asset.immich_id].exif_info
        db.add(
            LocationChange(
                asset_id=asset.id,
                prev_latitude=exif.latitude if exif else None,
                prev_longitude=exif.longitude if exif else None,
                latitude=latitude,
                longitude=longitude,
                source="manual",
                tag_added=asset.immich_id in tagged,
                status="applied",
                batch_id=result.batch_id,
            )
        )
        _set_local_location(asset, latitude, longitude)
        # A located photo is no longer skipped or "not applicable".
        asset.review_status = "new"
    result.written = len(targets)
    await embeddings.refresh_located(db, account_id=targets[0].account_id)
    await db.commit()
    return result


@dataclass
class BatchUndo:
    undone: int = 0
    # Changed since the write (in Immich, or by a later write here): never overwritten.
    changed: int = 0
    # Immich kept (0, 0) instead of clearing: the written location stays.
    failed: int = 0


async def undo_batch(
    db: AsyncSession, client: ImmichClient, account_id: UUID, batch_id: UUID, *, tag: str
) -> BatchUndo:
    """Restores the coordinates a batch replaced, where nothing changed them since."""
    rows = (
        await db.execute(
            select(LocationChange, Asset)
            .join(Asset, Asset.id == LocationChange.asset_id)
            .where(
                LocationChange.batch_id == batch_id,
                LocationChange.status == "applied",
                Asset.account_id == account_id,
            )
        )
    ).all()
    if not rows:
        raise ApiError(409, "location_nothing_to_undo")
    written_at = min(change.created_at for change, _ in rows)
    later = set(
        await db.scalars(
            select(LocationChange.asset_id).where(
                LocationChange.asset_id.in_([asset.id for _, asset in rows]),
                LocationChange.status == "applied",
                LocationChange.created_at > written_at,
                LocationChange.batch_id.is_distinct_from(batch_id),
            )
        )
    )
    current = await _read_all(client, [asset for _, asset in rows])
    result = BatchUndo()
    restore: list[tuple[LocationChange, Asset]] = []
    clear: list[tuple[LocationChange, Asset]] = []
    writes: list[Awaitable[None]] = []
    for change, asset in rows:
        exif = current[asset.immich_id].exif_info
        ours = (
            exif is not None
            and _same(exif.latitude, change.latitude)
            and _same(exif.longitude, change.longitude)
        )
        if asset.id in later or not ours:
            result.changed += 1
        elif change.prev_latitude is None or change.prev_longitude is None:
            clear.append((change, asset))
        else:
            restore.append((change, asset))
            writes.append(
                client.set_location(asset.immich_id, change.prev_latitude, change.prev_longitude)
            )

    await _gather(writes)
    cleared = await _clear_locations(client, clear)
    result.failed = len(clear) - len(cleared)
    done = restore + [(c, a) for c, a in clear if a.immich_id in cleared]
    untag = [a.immich_id for c, a in done if c.tag_added]
    if tag and untag:
        await _change_tags(client, tag, untag, add=False)

    now = datetime.now(UTC)
    for change, asset in done:
        change.status = "undone"
        change.undone_at = now
        _set_local_location(asset, change.prev_latitude, change.prev_longitude)
    result.undone = len(done)
    await embeddings.refresh_located(db, account_id=account_id)
    await db.commit()
    return result


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


async def _clear_locations(
    client: ImmichClient, pairs: list[tuple[LocationChange, Asset]]
) -> set[UUID]:
    """Clears the locations through (0, 0) in one request; returns the Immich ids cleared. Where
    Immich kept (0, 0), the written location is put back, as in `_clear_location`."""
    if not pairs:
        return set()
    waiting = {asset.immich_id: change for change, asset in pairs}
    await client.set_locations(list(waiting), 0.0, 0.0)
    cleared: set[UUID] = set()
    for _ in range(CLEAR_ATTEMPTS):
        await asyncio.sleep(CLEAR_POLL_S)
        for immich_id, item in (await _read_ids(client, list(waiting))).items():
            if not _has_location(item):
                cleared.add(immich_id)
                del waiting[immich_id]
        if not waiting:
            break
    await _gather([client.set_location(i, c.latitude, c.longitude) for i, c in waiting.items()])
    return cleared


async def _read_all(client: ImmichClient, assets: list[Asset]) -> dict[UUID, ImmichAsset]:
    return await _read_ids(client, [a.immich_id for a in assets])


async def _read_ids(client: ImmichClient, ids: list[UUID]) -> dict[UUID, ImmichAsset]:
    found = await _gather([client.asset(i) for i in ids])
    return dict(zip(ids, found, strict=True))


async def _gather[T](calls: list[Awaitable[T]]) -> list[T]:
    """Awaits the calls, at most CONCURRENCY at a time; results in the order of the calls."""
    limit = asyncio.Semaphore(CONCURRENCY)

    async def one(call: Awaitable[T]) -> T:
        async with limit:
            return await call

    return list(await asyncio.gather(*(one(call) for call in calls)))


def _has_location(item: ImmichAsset) -> bool:
    exif = item.exif_info
    return exif is not None and exif.latitude is not None and exif.longitude is not None


async def _change_tags(
    client: ImmichClient, tag: str, asset_ids: list[UUID], *, add: bool
) -> set[UUID]:
    try:
        tag_id = await client.upsert_tag(tag)
        if add:
            return await client.tag_assets(tag_id, asset_ids)
        return await client.untag_assets(tag_id, asset_ids)
    except ImmichError as exc:
        action = "add" if add else "remove"
        log.warning("Could not %s tag %r on %d assets: %s", action, tag, len(asset_ids), exc)
        return set()


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
