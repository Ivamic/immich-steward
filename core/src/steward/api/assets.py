# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gallery API: month buckets, assets, filter options and images proxied from Immich."""

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel

from steward.deps import CurrentAccount, DbDep, SecretBoxDep
from steward.errors import ApiError
from steward.gallery import (
    GalleryFilter,
    LocationFilter,
    TypeFilter,
    album_options,
    camera_options,
    month_assets_query,
    month_buckets,
)
from steward.immich import ImmichAuthError, ImmichError, ImmichUnreachableError
from steward.immich.thumbnails import ThumbnailFetcher, ThumbnailSize
from steward.models import Asset

router = APIRouter(prefix="/assets")

# Thumbnails change only when the asset changes in Immich; the ETag covers that.
IMAGE_CACHE_CONTROL = "private, max-age=604800"


def gallery_filter(
    location: LocationFilter = "all",
    type: TypeFilter = "all",
    camera: str | None = None,
    album: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    archived: bool = False,
) -> GalleryFilter:
    return GalleryFilter(
        location=location,
        type=type,
        camera=camera,
        album_id=album,
        date_from=date_from,
        date_to=date_to,
        include_archived=archived,
    )


FilterDep = Annotated[GalleryFilter, Depends(gallery_filter)]


class MonthBucket(BaseModel):
    month: str  # YYYY-MM
    count: int


class AssetItem(BaseModel):
    id: UUID
    local_taken_at: datetime
    type: str
    file_name: str
    has_location: bool
    width: int | None
    height: int | None

    @classmethod
    def of(cls, asset: Asset) -> "AssetItem":
        return cls(
            id=asset.id,
            local_taken_at=asset.local_taken_at,
            type=asset.type,
            file_name=asset.original_file_name,
            has_location=asset.latitude is not None,
            width=asset.width,
            height=asset.height,
        )


class CameraOption(BaseModel):
    value: str
    make: str
    model: str
    count: int


class AlbumOption(BaseModel):
    id: UUID
    name: str
    count: int


class FilterOptions(BaseModel):
    cameras: list[CameraOption]
    albums: list[AlbumOption]


@router.get("/months")
async def months(account: CurrentAccount, db: DbDep, filters: FilterDep) -> list[MonthBucket]:
    buckets = await month_buckets(db, account, filters)
    return [MonthBucket(month=f"{month:%Y-%m}", count=count) for month, count in buckets]


@router.get("")
async def list_month(
    account: CurrentAccount,
    db: DbDep,
    filters: FilterDep,
    month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
) -> list[AssetItem]:
    first_day = date.fromisoformat(f"{month}-01")
    assets = await db.scalars(month_assets_query(account, filters, first_day))
    return [AssetItem.of(asset) for asset in assets]


@router.get("/filter-options")
async def filter_options(account: CurrentAccount, db: DbDep) -> FilterOptions:
    return FilterOptions(
        cameras=[CameraOption(**row) for row in await camera_options(db, account)],
        albums=[AlbumOption(**row) for row in await album_options(db, account)],
    )


@router.get("/{asset_id}/thumbnail")
async def thumbnail(
    asset_id: UUID,
    request: Request,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    size: ThumbnailSize = "thumbnail",
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.account_id != account.id:
        raise ApiError(404, "asset_not_found")

    etag = f'"{asset.immich_id}-{asset.immich_updated_at.timestamp():.0f}-{size}"'
    headers = {"ETag": etag, "Cache-Control": IMAGE_CACHE_CONTROL}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)

    fetcher: ThumbnailFetcher = request.app.state.thumbnails
    try:
        image = await fetcher.fetch(box.decrypt(account.api_key_encrypted), asset.immich_id, size)
    except ImmichUnreachableError as exc:
        raise ApiError(502, "immich_unreachable") from exc
    except ImmichAuthError as exc:
        raise ApiError(502, "immich_invalid_api_key") from exc
    except ImmichError as exc:
        raise ApiError(502, "immich_error") from exc
    return Response(content=image.content, media_type=image.media_type, headers=headers)
