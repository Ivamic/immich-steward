# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gallery API: month buckets, assets, filter options and images proxied from Immich."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from steward import locations, rotation, worker_queue
from steward.config import Settings
from steward.deps import (
    CurrentAccount,
    DbDep,
    ImmichFactoryDep,
    SecretBoxDep,
    SettingsDep,
)
from steward.errors import ApiError
from steward.gallery import (
    GalleryFilter,
    ShowCategory,
    TypeFilter,
    album_options,
    camera_options,
    geoclip_confident_ids,
    month_assets_query,
    month_buckets,
    neighbors,
)
from steward.images import TURNS, UnreadableImage, turned
from steward.immich import (
    ImmichAuthError,
    ImmichClient,
    ImmichError,
    ImmichPermissionError,
    ImmichUnreachableError,
)
from steward.immich.compat import EDIT_PERMISSIONS
from steward.immich.thumbnails import ThumbnailFetcher, ThumbnailSize
from steward.models import Account, Album, Asset, AssetAlbum, LocationChange, ModuleRun
from steward.modules import MODULES, REMOTE_MODULES, ModuleContext, RemoteModule, similar

router = APIRouter(prefix="/assets")

# Thumbnails change only when the asset changes in Immich; the ETag covers that.
IMAGE_CACHE_CONTROL = "private, max-age=604800"


def gallery_filter(
    settings: SettingsDep,
    show: Annotated[list[ShowCategory] | None, Query()] = None,
    type: TypeFilter = "all",
    camera: str | None = None,
    album: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    archived: bool = False,
    geoclip_confident: bool = False,
    failed_module: Annotated[str | None, Query(max_length=32)] = None,
    failure: Annotated[str | None, Query(max_length=32)] = None,
) -> GalleryFilter:
    return GalleryFilter(
        show=frozenset(show or ()),
        type=type,
        camera=camera,
        album_id=album,
        date_from=date_from,
        date_to=date_to,
        include_archived=archived,
        geoclip_confidence=settings.geoclip_confident_from if geoclip_confident else None,
        failed_module=failed_module,
        failure=failure if failed_module else None,
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
    # No location yet, but GeoCLIP places the photo confidently.
    geoclip_confident: bool = False
    width: int | None
    height: int | None
    # Changes with the thumbnails (photo rotated or edited in Immich): for their addresses.
    version: str | None = None

    @classmethod
    def of(cls, asset: Asset, geoclip_confident: bool = False) -> "AssetItem":
        return cls(
            geoclip_confident=geoclip_confident,
            id=asset.id,
            local_taken_at=asset.local_taken_at,
            type=asset.type,
            file_name=asset.original_file_name,
            has_location=asset.latitude is not None,
            width=asset.width,
            height=asset.height,
            version=asset.thumbhash,
        )


class LocationChangeItem(BaseModel):
    id: UUID
    created_at: datetime
    latitude: float
    longitude: float
    prev_latitude: float | None
    prev_longitude: float | None
    source: str
    status: Literal["applied", "undone"]

    @classmethod
    def of(cls, change: LocationChange) -> "LocationChangeItem":
        return cls(
            id=change.id,
            created_at=change.created_at,
            latitude=change.latitude,
            longitude=change.longitude,
            prev_latitude=change.prev_latitude,
            prev_longitude=change.prev_longitude,
            source=change.source,
            status=change.status,
        )


class AssetDetail(BaseModel):
    id: UUID
    type: str
    file_name: str
    local_taken_at: datetime
    taken_at: datetime | None
    time_zone: str | None
    camera_make: str | None
    camera_model: str | None
    lens_model: str | None
    width: int | None
    height: int | None
    latitude: float | None
    longitude: float | None
    city: str | None
    state: str | None
    country: str | None
    review_status: str
    albums: list[str]
    # Newest first.
    location_history: list[LocationChangeItem]
    # There is an applied change to undo.
    can_undo: bool
    # Neighbors in the gallery order under the filter passed with the request.
    previous_id: UUID | None
    next_id: UUID | None
    # The photo in the Immich web UI.
    immich_url: str | None = None
    # Changes with the thumbnails (photo rotated or edited in Immich): for their addresses.
    version: str | None = None


class ReviewUpdate(BaseModel):
    status: Literal["new", "skipped", "not_applicable"]


class LocationUpdate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RegionIn(BaseModel):
    """A part of the photo as shares of its width and height (FR-35)."""

    x: float = Field(ge=0, lt=1)
    y: float = Field(ge=0, lt=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside(self) -> "RegionIn":
        if self.x + self.w > 1 + 1e-6 or self.y + self.h > 1 + 1e-6:
            raise ValueError("the region must lie inside the photo")
        return self


class CandidateItem(BaseModel):
    rank: int  # 1-based, within the module
    latitude: float
    longitude: float
    score: float
    radius_m: float | None
    kind: str
    evidence: dict[str, Any]
    # weak: shown folded ("probably only the region is right"); confident: marked in the list.
    tier: Literal["weak", "normal", "confident"] = "normal"


def _thresholds(module_id: str, settings: Settings) -> tuple[float, float, float]:
    """Display minimum, "weak" below, "confident" from: each module has its own score scale."""
    if module_id == similar.MODULE_ID:
        return (
            settings.similar_min_confidence,
            settings.similar_weak_below,
            settings.similar_confident_from,
        )
    return (
        settings.geoclip_min_confidence,
        settings.geoclip_weak_below,
        settings.geoclip_confident_from,
    )


def _tier(
    score: float, weak_below: float, confident_from: float
) -> Literal["weak", "normal", "confident"]:
    if score < weak_below:
        return "weak"
    if score >= confident_from:
        return "confident"
    return "normal"


class TrackPointItem(BaseModel):
    asset_id: UUID
    latitude: float
    longitude: float
    local_taken_at: datetime
    delta_s: float
    file_name: str
    camera: str
    same_camera: bool
    estimated: bool
    role: Literal["before", "after"] | None


class CameraCountItem(BaseModel):
    value: str
    label: str
    count: int
    same_camera: bool
    excluded: bool


class ModuleSuggestions(BaseModel):
    module: str
    version: str
    color: str
    shape: str
    candidates: list[CandidateItem]
    track: list[TrackPointItem]
    cameras: list[CameraCountItem]
    note: str | None
    # ready: computed now (core modules) or a finished run; not_run: never run on this photo.
    status: Literal["ready", "not_run", "queued", "running", "done", "failed"] = "ready"
    # Run by workers: can be started (again) from the card.
    runnable: bool = False
    # A worker that runs the module has contacted the core recently.
    worker_available: bool = True
    error: str | None = None
    # Why the latest run failed (`worker_queue.FAILURE_CODES`).
    error_code: str | None = None
    finished_at: datetime | None = None
    # Queued runs: jobs of the module a worker takes before this one.
    queue_position: int | None = None
    # Background runs of the module are paused (a run by hand still goes).
    paused: bool = False
    # A worker of the module is downloading or loading its model: the next run takes longer.
    worker_loading: bool = False
    # Tells the block apart: the module id, or "<module>:region" for its run on a part.
    key: str = ""
    # The part of the photo of a run on a part (FR-35).
    region: RegionIn | None = None
    # The run was on the photo turned this many degrees clockwise.
    turn: int = 0


class RunRequest(BaseModel):
    # None: the whole photo.
    region: RegionIn | None = None
    # The photo as the user turned it, clockwise; the region is on the turned photo.
    turn: Literal[0, 90, 180, 270] = 0


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
    settings: SettingsDep,
    month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
) -> list[AssetItem]:
    first_day = date.fromisoformat(f"{month}-01")
    assets = list(await db.scalars(month_assets_query(account, filters, first_day)))
    confident = await geoclip_confident_ids(
        db, [a.id for a in assets], settings.geoclip_confident_from
    )
    return [AssetItem.of(asset, asset.id in confident) for asset in assets]


@router.get("/filter-options")
async def filter_options(account: CurrentAccount, db: DbDep) -> FilterOptions:
    return FilterOptions(
        cameras=[CameraOption(**row) for row in await camera_options(db, account)],
        albums=[AlbumOption(**row) for row in await album_options(db, account)],
    )


async def _own_asset(db: DbDep, account: CurrentAccount, asset_id: UUID) -> Asset:
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.account_id != account.id:
        raise ApiError(404, "asset_not_found")
    return asset


async def _detail(
    db: DbDep, account: CurrentAccount, asset: Asset, filters: GalleryFilter, settings: Settings
) -> AssetDetail:
    albums = await db.scalars(
        select(Album.name)
        .join(AssetAlbum, AssetAlbum.album_id == Album.id)
        .where(AssetAlbum.asset_id == asset.id)
        .order_by(Album.name)
    )
    previous_id, next_id = await neighbors(db, account, filters, asset)
    history = await locations.history(db, asset)
    last_applied = next((c for c in history if c.status == "applied"), None)
    return AssetDetail(
        id=asset.id,
        type=asset.type,
        file_name=asset.original_file_name,
        local_taken_at=asset.local_taken_at,
        taken_at=asset.taken_at,
        time_zone=asset.time_zone,
        camera_make=asset.camera_make,
        camera_model=asset.camera_model,
        lens_model=asset.lens_model,
        width=asset.width,
        height=asset.height,
        latitude=asset.latitude,
        longitude=asset.longitude,
        city=asset.city,
        state=asset.state,
        country=asset.country,
        review_status=asset.review_status,
        albums=list(albums),
        location_history=[LocationChangeItem.of(change) for change in history],
        can_undo=last_applied is not None,
        previous_id=previous_id,
        next_id=next_id,
        immich_url=(
            f"{settings.immich_browser_url}/photos/{asset.immich_id}"
            if settings.immich_browser_url
            else None
        ),
        version=asset.thumbhash,
    )


@router.get("/{asset_id}")
async def get_asset(
    asset_id: UUID, account: CurrentAccount, db: DbDep, filters: FilterDep, settings: SettingsDep
) -> AssetDetail:
    asset = await _own_asset(db, account, asset_id)
    return await _detail(db, account, asset, filters, settings)


@router.put("/{asset_id}/review")
async def set_review(
    asset_id: UUID,
    body: ReviewUpdate,
    account: CurrentAccount,
    db: DbDep,
    filters: FilterDep,
    settings: SettingsDep,
) -> AssetDetail:
    """Marks the photo as skipped / not applicable, or returns it to the to-do list."""
    asset = await _own_asset(db, account, asset_id)
    asset.review_status = body.status
    await db.commit()
    return await _detail(db, account, asset, filters, settings)


@router.get("/{asset_id}/suggestions")
async def suggestions(
    asset_id: UUID,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    exclude_camera: Annotated[list[str] | None, Query()] = None,
    same_camera_only: bool = False,
) -> list[ModuleSuggestions]:
    """Candidates of the core modules (computed now) and the latest results of worker modules."""
    asset = await _own_asset(db, account, asset_id)
    cameras = frozenset(exclude_camera or ())
    return await _suggestions(db, account, asset, settings, cameras, same_camera_only)


@router.post("/{asset_id}/modules/{module_id}/run")
async def run_module(
    asset_id: UUID,
    module_id: str,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    exclude_camera: Annotated[list[str] | None, Query()] = None,
    same_camera_only: bool = False,
    body: RunRequest | None = None,
) -> list[ModuleSuggestions]:
    """Queues a worker module for the photo, or a part of it, ahead of the background runs
    (FR-34, FR-35)."""
    if module_id not in REMOTE_MODULES:
        raise ApiError(404, "module_not_found")
    asset = await _own_asset(db, account, asset_id)
    region = body.region.model_dump() if body and body.region else None
    turn = body.turn if body else 0
    await worker_queue.enqueue_module(
        db, asset, module_id, worker_queue.PRIORITY_USER, region, turn
    )
    cameras = frozenset(exclude_camera or ())
    return await _suggestions(db, account, asset, settings, cameras, same_camera_only)


async def _suggestions(
    db: DbDep,
    account: Account,
    asset: Asset,
    settings: SettingsDep,
    exclude_cameras: frozenset[str],
    same_camera_only: bool = False,
) -> list[ModuleSuggestions]:
    ctx = ModuleContext(
        db=db,
        account=account,
        asset=asset,
        settings=settings,
        exclude_cameras=exclude_cameras,
        same_camera_only=same_camera_only,
    )
    result = []
    for module in MODULES:
        found = await module.run(ctx)
        result.append(
            ModuleSuggestions(
                module=module.id,
                version=module.version,
                color=module.color,
                shape=module.shape,
                candidates=[
                    CandidateItem(rank=rank, **vars(candidate))
                    for rank, candidate in enumerate(found.candidates, start=1)
                ],
                track=[TrackPointItem(**vars(point)) for point in found.track],
                cameras=[CameraCountItem(**vars(camera)) for camera in found.cameras],
                note=found.note,
                key=module.id,
            )
        )

    runs = await worker_queue.latest_runs(db, asset.id)
    region_runs = await worker_queue.latest_runs(db, asset.id, region=True)
    workers = await worker_queue.active_workers(
        db, timedelta(minutes=settings.worker_active_minutes)
    )
    available = {module for worker in workers for module in worker.modules}
    loading = {w.state_module for w in workers if w.state in worker_queue.MODEL_STATES}
    paused = await worker_queue.paused_modules(db)
    for remote in REMOTE_MODULES.values():
        whole = await _remote(db, asset, remote, runs.get(remote.id), available, settings)
        whole.paused = worker_queue.is_paused(paused, remote.id)
        whole.worker_loading = remote.id in loading
        result.append(whole)
        # The run on a part of the photo, if any, right after the one on the whole photo.
        if run := region_runs.get(remote.id):
            result.append(await _remote(db, asset, remote, run, available, settings))
    return result


async def _remote(
    db: DbDep,
    asset: Asset,
    remote: RemoteModule,
    run: ModuleRun | None,
    available: set[str],
    settings: Settings,
) -> ModuleSuggestions:
    region = RegionIn(**run.region) if run and run.region else None
    minimum, weak_below, confident_from = _thresholds(remote.id, settings)
    found: list[dict[str, Any]] = []
    if run and run.status == "done":
        if remote.id == similar.MODULE_ID:
            # Searched now, so that it sees the library as it is (D-105).
            found = [
                vars(candidate)
                for candidate in await similar.suggest(
                    db, run, asset.account_id, asset.local_taken_at, settings
                )
            ]
        else:
            found = run.candidates
    return ModuleSuggestions(
        module=remote.id,
        version=(run.module_version if run else None) or "",
        color=remote.color,
        shape=remote.shape,
        candidates=[
            CandidateItem(
                rank=rank, tier=_tier(candidate["score"], weak_below, confident_from), **candidate
            )
            for rank, candidate in enumerate([c for c in found if c["score"] >= minimum], start=1)
        ],
        track=[],
        cameras=[],
        note=None,
        status=run.status if run else "not_run",
        runnable=True,
        worker_available=remote.id in available,
        error=run.error if run else None,
        error_code=run.error_code if run else None,
        finished_at=run.finished_at if run else None,
        queue_position=await worker_queue.queue_position(db, run) if run else None,
        key=f"{remote.id}:region" if region else remote.id,
        region=region,
        turn=run.turn if run else 0,
    )


@asynccontextmanager
async def _immich(
    settings: SettingsDep, factory: ImmichFactoryDep, box: SecretBoxDep, account: Account
) -> AsyncIterator[ImmichClient]:
    """An Immich client for the account; Immich failures become API errors."""
    assert settings.immich_url is not None  # guaranteed by SecretBoxDep
    try:
        async with factory(settings.immich_url, box.decrypt(account.api_key_encrypted)) as client:
            yield client
    except ImmichError as exc:
        raise _api_error(exc) from exc


def _api_error(exc: ImmichError) -> ApiError:
    if isinstance(exc, ImmichUnreachableError):
        return ApiError(502, "immich_unreachable")
    if isinstance(exc, ImmichAuthError):
        return ApiError(502, "immich_invalid_api_key")
    if isinstance(exc, ImmichPermissionError):
        return ApiError(403, "immich_missing_permissions", permissions=[])
    return ApiError(502, "immich_error")


class RotateRequest(BaseModel):
    # Clockwise, on top of how the photo is shown now.
    turn: Literal[90, 180, 270]


@router.post("/{asset_id}/rotate")
async def rotate(
    asset_id: UUID,
    body: RotateRequest,
    account: CurrentAccount,
    db: DbDep,
    filters: FilterDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> AssetDetail:
    """Saves the photo rotated in Immich (as an edit; the original file is not changed)."""
    asset = await _own_asset(db, account, asset_id)
    try:
        async with _immich(settings, factory, box, account) as client:
            await rotation.save_turn(db, client, asset, body.turn)
    except ApiError as exc:
        if exc.code == "immich_missing_permissions":
            raise ApiError(403, exc.code, permissions=list(EDIT_PERMISSIONS)) from exc
        raise
    return await _detail(db, account, asset, filters, settings)


@router.put("/{asset_id}/location")
async def set_location(
    asset_id: UUID,
    body: LocationUpdate,
    account: CurrentAccount,
    db: DbDep,
    filters: FilterDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> AssetDetail:
    """Writes the location the user picked to Immich (FR-50)."""
    asset = await _own_asset(db, account, asset_id)
    async with _immich(settings, factory, box, account) as client:
        await locations.write_location(
            db,
            client,
            asset,
            body.latitude,
            body.longitude,
            source="manual",
            tag=settings.estimated_tag,
        )
    return await _detail(db, account, asset, filters, settings)


@router.post("/{asset_id}/location/undo")
async def undo_location(
    asset_id: UUID,
    account: CurrentAccount,
    db: DbDep,
    filters: FilterDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> AssetDetail:
    """Restores the coordinates replaced by the last write (FR-51)."""
    asset = await _own_asset(db, account, asset_id)
    async with _immich(settings, factory, box, account) as client:
        await locations.undo_last(db, client, asset, tag=settings.estimated_tag)
    return await _detail(db, account, asset, filters, settings)


@router.get("/{asset_id}/thumbnail")
async def thumbnail(
    asset_id: UUID,
    request: Request,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    size: ThumbnailSize = "thumbnail",
    turn: int = 0,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    """The photo as Immich shows it, or turned clockwise as the user turned it in the app."""
    if turn not in TURNS:
        raise ApiError(422, "turn_invalid")
    asset = await _own_asset(db, account, asset_id)
    etag = f'"{asset.immich_id}-{asset.immich_updated_at.timestamp():.0f}-{size}-{turn}"'
    headers = {"ETag": etag, "Cache-Control": IMAGE_CACHE_CONTROL}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)

    fetcher: ThumbnailFetcher = request.app.state.thumbnails
    try:
        image = await fetcher.fetch(
            box.decrypt(account.api_key_encrypted), asset.immich_id, size, asset.is_edited
        )
    except ImmichError as exc:
        raise _api_error(exc) from exc
    if not turn:
        return Response(content=image.content, media_type=image.media_type, headers=headers)
    try:
        content = await asyncio.to_thread(turned, image.content, turn)
    except UnreadableImage as exc:
        raise ApiError(422, "image_invalid") from exc
    return Response(content=content, media_type="image/jpeg", headers=headers)
