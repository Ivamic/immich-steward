# SPDX-License-Identifier: AGPL-3.0-or-later
"""Albums (D-233): the list for the Albums page and the album picker, and changes made in
Immich on the user's click: adding and removing photos, creating, renaming, deleting."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select

from steward import albums
from steward.api.assets import IMAGE_CACHE_CONTROL, _api_error, _immich
from steward.api.selection import AssetIds
from steward.deps import CurrentAccount, DbDep, ImmichFactoryDep, SecretBoxDep, SettingsDep
from steward.errors import ApiError
from steward.immich import ImmichClient, ImmichError
from steward.immich.compat import ALBUM_PERMISSIONS, has_permission
from steward.immich.thumbnails import ThumbnailFetcher
from steward.models import Account, Album, AssetAlbum

router = APIRouter(prefix="/albums")

AlbumName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=albums.NAME_MAX)
]
AlbumAction = Literal["add", "remove", "create", "rename", "delete"]


class AlbumOut(BaseModel):
    id: UUID
    immich_id: UUID
    name: str
    # Photos in the album as Immich counts them (in a shared album, other users' too).
    count: int
    # Of them, photos of this account's library: what the gallery shows with the album filter.
    own_count: int
    shared: bool
    role: str
    # The album may get and lose photos; and be renamed or deleted (only by its owner).
    can_change_photos: bool
    owned: bool
    has_cover: bool
    start_date: datetime | None
    end_date: datetime | None
    updated_at: datetime


class AlbumList(BaseModel):
    albums: list[AlbumOut]
    # What the API key lets the app do with albums; the others are shown as unavailable.
    allowed: dict[AlbumAction, bool]
    # The Immich permission each action needs, for the explanation.
    permissions: dict[AlbumAction, str]
    # Immich in the browser, for links to the albums there (`/albums/{immich_id}`).
    immich_url: str | None


class AddIn(BaseModel):
    ids: AssetIds


class CreateIn(BaseModel):
    name: AlbumName
    ids: list[UUID] = Field(default_factory=list, max_length=2000)


class RenameIn(BaseModel):
    name: AlbumName


class AddedOut(BaseModel):
    album: AlbumOut
    # Local ids of the photos put into the album now: what an undo removes again.
    added: list[UUID]
    already: int
    skipped_locked: int
    failed: int
    # The album was made by this change: undoing it deletes the album.
    created: bool


class RemovedOut(BaseModel):
    album: AlbumOut
    removed: int
    failed: int


@router.get("")
async def album_list(
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> AlbumList:
    """The account's albums and the ones shared with it, by name."""
    async with _immich(settings, factory, box, account) as client:
        granted = (await client.api_key_info()).permissions
    rows = await db.scalars(
        select(Album).where(Album.account_id == account.id).order_by(func.lower(Album.name))
    )
    found = list(rows)
    counts = await _own_counts(db, [a.id for a in found])
    return AlbumList(
        albums=[_out(album, counts.get(album.id, 0)) for album in found],
        allowed={
            action: has_permission(granted, permission)
            for action, permission in ALBUM_PERMISSIONS.items()
        },
        permissions=dict(ALBUM_PERMISSIONS),
        immich_url=settings.immich_browser_url,
    )


@router.post("")
async def create(
    body: CreateIn,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> AddedOut:
    """A new album in Immich, with the photos given (possibly none)."""
    assets = await albums.own_assets(db, account, body.ids)
    async with _album_change(settings, factory, box, account, "create") as client:
        result = await albums.create_album(db, client, account, body.name, assets)
    return await _added(db, result, created=True)


@router.put("/{album_id}/assets")
async def add(
    album_id: UUID,
    body: AddIn,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> AddedOut:
    album = await _album(db, account, album_id)
    if not albums.can_change_photos(album):
        raise ApiError(403, "album_read_only")
    assets = await albums.own_assets(db, account, body.ids)
    async with _album_change(settings, factory, box, account, "add") as client:
        result = await albums.add_assets(db, client, album, assets)
    return await _added(db, result, created=False)


@router.post("/{album_id}/assets/remove")
async def remove(
    album_id: UUID,
    body: AddIn,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> RemovedOut:
    """Takes photos out of the album (they stay in Immich); also the undo of adding them."""
    album = await _album(db, account, album_id)
    if not albums.can_change_photos(album):
        raise ApiError(403, "album_read_only")
    assets = await albums.own_assets(db, account, body.ids)
    async with _album_change(settings, factory, box, account, "remove") as client:
        result = await albums.remove_assets(db, client, album, assets)
    count = (await _own_counts(db, [album.id])).get(album.id, 0)
    return RemovedOut(album=_out(album, count), removed=result.removed, failed=result.failed)


@router.patch("/{album_id}")
async def rename(
    album_id: UUID,
    body: RenameIn,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> AlbumOut:
    album = await _album(db, account, album_id)
    if not albums.is_owned(album):
        raise ApiError(403, "album_not_owned")
    async with _album_change(settings, factory, box, account, "rename") as client:
        await albums.rename_album(db, client, album, body.name)
    count = (await _own_counts(db, [album.id])).get(album.id, 0)
    return _out(album, count)


@router.delete("/{album_id}", status_code=204)
async def delete(
    album_id: UUID,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> None:
    """Deletes the album in Immich; its photos stay in the library."""
    album = await _album(db, account, album_id)
    if not albums.is_owned(album):
        raise ApiError(403, "album_not_owned")
    async with _album_change(settings, factory, box, account, "delete") as client:
        await albums.delete_album(db, client, album)


@router.get("/{album_id}/cover")
async def cover(
    album_id: UUID,
    request: Request,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
) -> Response:
    """The cover photo of the album, possibly another user's in a shared album."""
    album = await _album(db, account, album_id)
    if album.thumbnail_immich_id is None:
        raise ApiError(404, "album_no_cover")
    etag = f'"{album.thumbnail_immich_id}-{album.immich_updated_at.timestamp():.0f}"'
    headers = {"ETag": etag, "Cache-Control": IMAGE_CACHE_CONTROL}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    fetcher: ThumbnailFetcher = request.app.state.thumbnails
    try:
        image = await fetcher.fetch(
            box.decrypt(account.api_key_encrypted), album.thumbnail_immich_id, "thumbnail"
        )
    except ImmichError as exc:
        raise _api_error(exc) from exc
    return Response(content=image.content, media_type=image.media_type, headers=headers)


@asynccontextmanager
async def _album_change(
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
    account: Account,
    action: AlbumAction,
) -> AsyncIterator[ImmichClient]:
    """An Immich client for one album change; a refusal names the permission it needs."""
    try:
        async with _immich(settings, factory, box, account) as client:
            yield client
    except ApiError as exc:
        if exc.code == "immich_missing_permissions":
            permission = ALBUM_PERMISSIONS[action]
            raise ApiError(403, exc.code, permissions=[permission]) from exc
        raise


async def _album(db: DbDep, account: Account, album_id: UUID) -> Album:
    album = await db.get(Album, album_id)
    if album is None or album.account_id != account.id:
        raise ApiError(404, "album_not_found")
    return album


async def _own_counts(db: DbDep, album_ids: list[UUID]) -> dict[UUID, int]:
    if not album_ids:
        return {}
    rows = await db.execute(
        select(AssetAlbum.album_id, func.count())
        .where(AssetAlbum.album_id.in_(album_ids))
        .group_by(AssetAlbum.album_id)
    )
    return {row[0]: row[1] for row in rows}


async def _added(db: DbDep, result: albums.Added, *, created: bool) -> AddedOut:
    count = (await _own_counts(db, [result.album.id])).get(result.album.id, 0)
    return AddedOut(
        album=_out(result.album, count),
        added=result.added,
        already=result.already,
        skipped_locked=result.skipped_locked,
        failed=result.failed,
        created=created,
    )


def _out(album: Album, own_count: int) -> AlbumOut:
    return AlbumOut(
        id=album.id,
        immich_id=album.immich_id,
        name=album.name,
        count=album.asset_count,
        own_count=own_count,
        shared=album.shared,
        role=album.role,
        can_change_photos=albums.can_change_photos(album),
        owned=albums.is_owned(album),
        has_cover=album.thumbnail_immich_id is not None,
        start_date=album.start_date,
        end_date=album.end_date,
        updated_at=album.immich_updated_at,
    )
