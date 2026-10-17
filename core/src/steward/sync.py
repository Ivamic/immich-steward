# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synchronization of assets and albums from Immich into the local database.

A full sync walks the whole library and removes local assets that Immich no longer returns.
An incremental sync only fetches assets changed since the previous sync; deletions are picked
up by the next full sync.
"""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from steward.immich import ImmichClient
from steward.immich.models import ImmichAlbum, ImmichAsset
from steward.models import Account, Album, Asset, AssetAlbum

# "hidden" are the video parts of live photos, "locked" is the locked folder (not accessible
# with API keys anyway).
SYNCED_VISIBILITIES = ("timeline", "archive")

# Overlap with the previous incremental sync, to tolerate clock skew between the servers.
INCREMENTAL_OVERLAP = timedelta(minutes=5)

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class SyncStats:
    full: bool
    assets: int = 0
    removed: int = 0
    albums: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "full": self.full,
            "assets": self.assets,
            "removed": self.removed,
            "albums": self.albums,
        }


async def sync_account(
    db: AsyncSession,
    client: ImmichClient,
    account: Account,
    *,
    full: bool,
    on_progress: ProgressCallback | None = None,
) -> SyncStats:
    started = datetime.now(UTC)
    updated_after: datetime | None = None
    if full or account.synced_at is None:
        full = True
    else:
        updated_after = account.synced_at - INCREMENTAL_OVERLAP
    stats = SyncStats(full=full)

    for visibility in SYNCED_VISIBILITIES:
        page: int | None = 1
        while page is not None:
            result = await client.search_assets(
                page=page,
                visibility=visibility,
                updated_after=updated_after,
                with_deleted=True,
            )
            rows = [
                _asset_row(account, item, started)
                for item in result.items
                if item.owner_id == account.immich_user_id
            ]
            await _upsert_assets(db, rows)
            await db.commit()
            stats.assets += len(rows)
            if on_progress is not None:
                await on_progress(stats.as_dict())
            page = result.next_page

    if full:
        removed = await db.execute(
            delete(Asset).where(Asset.account_id == account.id, Asset.synced_at < started)
        )
        stats.removed = removed.rowcount  # type: ignore[attr-defined]

    stats.albums = await _sync_albums(db, client, account, refresh_all=full)

    account.synced_at = started
    if full:
        account.full_synced_at = started
    await db.commit()
    return stats


def _asset_row(account: Account, item: ImmichAsset, synced_at: datetime) -> dict[str, Any]:
    exif = item.exif_info
    return {
        "account_id": account.id,
        "immich_id": item.id,
        "type": item.type,
        "visibility": item.visibility,
        "is_trashed": item.is_trashed,
        "original_file_name": item.original_file_name,
        "file_created_at": item.file_created_at,
        # Immich encodes the local wall-clock time as if it were UTC; drop the fake zone.
        "local_taken_at": item.local_date_time.replace(tzinfo=None),
        "taken_at": exif.date_time_original if exif else None,
        "time_zone": exif.time_zone if exif else None,
        "camera_make": exif.make if exif else None,
        "camera_model": exif.model if exif else None,
        "lens_model": exif.lens_model if exif else None,
        "width": item.width,
        "height": item.height,
        "latitude": exif.latitude if exif else None,
        "longitude": exif.longitude if exif else None,
        "city": exif.city if exif else None,
        "state": exif.state if exif else None,
        "country": exif.country if exif else None,
        "checksum": item.checksum,
        "immich_updated_at": item.updated_at,
        "synced_at": synced_at,
    }


async def _upsert_assets(db: AsyncSession, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    statement = insert(Asset).values(rows)
    updated = {
        column: statement.excluded[column]
        for column in rows[0]
        if column not in ("account_id", "immich_id")
    }
    await db.execute(
        statement.on_conflict_do_update(index_elements=["account_id", "immich_id"], set_=updated)
    )


async def _sync_albums(
    db: AsyncSession, client: ImmichClient, account: Account, *, refresh_all: bool
) -> int:
    remote = await client.albums()
    local = {
        album.immich_id: album
        for album in await db.scalars(select(Album).where(Album.account_id == account.id))
    }

    for gone in set(local) - {album.id for album in remote}:
        await db.delete(local.pop(gone))

    for item in remote:
        album = local.get(item.id)
        changed = album is None or album.immich_updated_at != item.updated_at
        if album is None:
            album = Album(account_id=account.id, immich_id=item.id)
            db.add(album)
        album.name = item.album_name
        album.asset_count = item.asset_count
        album.shared = item.shared
        album.immich_updated_at = item.updated_at
        await db.flush()
        if changed or refresh_all:
            await _sync_album_members(db, client, account, album, item)
    await db.commit()
    return len(remote)


async def _sync_album_members(
    db: AsyncSession,
    client: ImmichClient,
    account: Account,
    album: Album,
    item: ImmichAlbum,
) -> None:
    immich_ids: list[UUID] = []
    page: int | None = 1
    while page is not None:
        result = await client.search_assets(page=page, album_id=item.id, with_exif=False)
        immich_ids.extend(asset.id for asset in result.items)
        page = result.next_page

    await db.execute(delete(AssetAlbum).where(AssetAlbum.album_id == album.id))
    for chunk in _chunks(immich_ids, 1000):
        asset_ids = await db.scalars(
            select(Asset.id).where(Asset.account_id == account.id, Asset.immich_id.in_(chunk))
        )
        rows = [{"asset_id": asset_id, "album_id": album.id} for asset_id in asset_ids]
        if rows:
            await db.execute(insert(AssetAlbum).values(rows).on_conflict_do_nothing())


def _chunks[T](items: list[T], size: int) -> Iterable[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


async def library_counts(db: AsyncSession, account: Account) -> dict[str, int]:
    """Asset counts shown on the home page (trashed assets excluded)."""
    live = (Asset.account_id == account.id, Asset.is_trashed.is_(False))
    row = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(Asset.type == "VIDEO"),
                func.count().filter(Asset.latitude.is_not(None)),
            ).where(*live)
        )
    ).one()
    albums = await db.scalar(
        select(func.count()).select_from(Album).where(Album.account_id == account.id)
    )
    total, videos, with_gps = row
    return {
        "assets": total,
        "videos": videos,
        "with_gps": with_gps,
        "without_gps": total - with_gps,
        "albums": albums or 0,
    }
