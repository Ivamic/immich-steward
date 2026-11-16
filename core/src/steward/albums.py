# SPDX-License-Identifier: AGPL-3.0-or-later
"""Changing albums in Immich from the app (D-233): adding and removing photos, creating,
renaming and deleting albums. Each change is made in Immich first, then mirrored in the local
tables, so that the album filter shows it before the next sync."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from steward.immich import ImmichClient
from steward.models import Account, Album, Asset, AssetAlbum
from steward.sync import apply_album

# Roles that may add photos to an album and remove them.
WRITE_ROLES = frozenset({"owner", "editor"})
NAME_MAX = 200


@dataclass
class Added:
    album: Album
    # Local ids of the photos this change put into the album: what an undo takes out again.
    added: list[UUID] = field(default_factory=list)
    already: int = 0
    # Photos of the locked folder: Immich keeps them out of albums.
    skipped_locked: int = 0
    failed: int = 0


@dataclass
class Removed:
    # Local ids of the photos taken out now: what an undo puts back.
    removed: list[UUID] = field(default_factory=list)
    failed: int = 0


def can_change_photos(album: Album) -> bool:
    return album.role in WRITE_ROLES


def is_owned(album: Album) -> bool:
    return album.role == "owner"


def _split_locked(assets: list[Asset]) -> tuple[list[Asset], int]:
    shown = [a for a in assets if a.visibility != "locked"]
    return shown, len(assets) - len(shown)


async def add_assets(
    db: AsyncSession, client: ImmichClient, album: Album, assets: list[Asset]
) -> Added:
    result = Added(album)
    assets, result.skipped_locked = _split_locked(assets)
    if not assets:
        return result
    by_immich = {a.immich_id: a for a in assets}
    answers = await client.add_to_album(album.immich_id, list(by_immich))
    present: list[UUID] = []
    for answer in answers:
        asset = by_immich.get(answer.id)
        if asset is None:
            continue
        if answer.success:
            result.added.append(asset.id)
            present.append(asset.id)
        elif answer.error == "duplicate":
            result.already += 1
            present.append(asset.id)
        else:
            result.failed += 1
    await _link(db, album, present)
    album.asset_count += len(result.added)
    if result.added:
        _touched(album)
    await db.commit()
    return result


async def remove_assets(
    db: AsyncSession, client: ImmichClient, album: Album, assets: list[Asset]
) -> Removed:
    result = Removed()
    if not assets:
        return result
    by_immich = {a.immich_id: a for a in assets}
    answers = await client.remove_from_album(album.immich_id, list(by_immich))
    gone: list[UUID] = []
    for answer in answers:
        asset = by_immich.get(answer.id)
        if asset is None:
            continue
        if answer.success:
            result.removed.append(asset.id)
            gone.append(asset.id)
        elif answer.error == "not_found":
            # Not in the album (any more): only the local copy was behind.
            gone.append(asset.id)
        else:
            result.failed += 1
    if gone:
        await db.execute(
            delete(AssetAlbum).where(AssetAlbum.album_id == album.id, AssetAlbum.asset_id.in_(gone))
        )
    album.asset_count = max(0, album.asset_count - len(result.removed))
    if result.removed:
        _touched(album)
    await db.commit()
    return result


async def create_album(
    db: AsyncSession, client: ImmichClient, account: Account, name: str, assets: list[Asset]
) -> Added:
    shown, skipped = _split_locked(assets)
    item = await client.create_album(name, [a.immich_id for a in shown])
    album = Album(account_id=account.id, immich_id=item.id)
    apply_album(album, item, account)
    db.add(album)
    await db.flush()
    await _link(db, album, [a.id for a in shown])
    await db.commit()
    return Added(album, added=[a.id for a in shown], skipped_locked=skipped)


async def rename_album(db: AsyncSession, client: ImmichClient, album: Album, name: str) -> None:
    item = await client.rename_album(album.immich_id, name)
    album.name = item.album_name
    album.immich_updated_at = item.updated_at
    await db.commit()


async def delete_album(db: AsyncSession, client: ImmichClient, album: Album) -> None:
    """Deletes the album in Immich; its photos stay."""
    await client.delete_album(album.immich_id)
    await db.delete(album)
    await db.commit()


async def own_assets(db: AsyncSession, account: Account, ids: list[UUID]) -> list[Asset]:
    """The account's photos among `ids`, in the order given; unknown ids are left out."""
    found = {
        a.id: a
        for a in await db.scalars(
            select(Asset).where(Asset.account_id == account.id, Asset.id.in_(ids))
        )
    }
    return [found[i] for i in dict.fromkeys(ids) if i in found]


def _touched(album: Album) -> None:
    """The album changed now: it goes first among the ones changed lately at once, not only after
    the next sync (which then reads its photos again, as for any change in Immich)."""
    album.immich_updated_at = datetime.now(UTC)


async def _link(db: AsyncSession, album: Album, asset_ids: list[UUID]) -> None:
    rows = [{"asset_id": asset_id, "album_id": album.id} for asset_id in asset_ids]
    if rows:
        await db.execute(insert(AssetAlbum).values(rows).on_conflict_do_nothing())
