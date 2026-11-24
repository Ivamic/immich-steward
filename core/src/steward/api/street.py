# SPDX-License-Identifier: AGPL-3.0-or-later
"""Street-level images near a point (`steward.street`, D-244): the sources of the account, the
images near a point and their previews, all through the core."""

from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic import BaseModel, Field

from steward import street, worker_queue
from steward.api.assets import _own_asset
from steward.api.maps import MapTransportDep
from steward.deps import CurrentAccount, DbDep, SecretBoxDep, SettingsDep
from steward.errors import ApiError

router = APIRouter(prefix="/street")

# Ids of both providers: Mapillary's are digits, Panoramax's UUIDs.
ImageId = Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,64}$")]


def get_links(request: Request) -> street.Links:
    links: street.Links = request.app.state.street_links
    return links


LinksDep = Annotated[street.Links, Depends(get_links)]


class StreetSourceOut(BaseModel):
    id: str
    name: str
    enabled: bool
    needs_key: bool
    has_key: bool
    key_problem: str | None
    site_url: str
    terms_url: str
    key_url: str | None


def _out(state: street.SourceState) -> StreetSourceOut:
    s = state.source
    return StreetSourceOut(
        id=s.id,
        name=s.name,
        enabled=state.enabled,
        needs_key=s.needs_key,
        has_key=state.has_key,
        key_problem=state.key_problem,
        site_url=s.site_url,
        terms_url=s.terms_url,
        key_url=s.key_url,
    )


@router.get("/sources")
async def get_sources(account: CurrentAccount, db: DbDep) -> list[StreetSourceOut]:
    return [_out(state) for state in await street.states(db, account.id)]


class StreetSourceUpdate(BaseModel):
    """Only the fields given change; an empty or null token deletes it."""

    enabled: bool | None = None
    api_key: str | None = Field(default=None, max_length=1000)


@router.put("/sources/{source_id}")
async def update_source(
    source_id: str,
    body: StreetSourceUpdate,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    transport: MapTransportDep,
) -> StreetSourceOut:
    """A new token is checked with the provider at once."""
    await street.update(
        db,
        box,
        account.id,
        source_id,
        enabled=body.enabled,
        api_key=body.api_key,
        key_given="api_key" in body.model_fields_set,
        transport=transport,
    )
    found = next(s for s in await street.states(db, account.id) if s.source.id == source_id)
    return _out(found)


class StreetImageOut(BaseModel):
    source: str
    id: str
    latitude: float
    longitude: float
    distance_m: float
    heading: float | None
    pano: bool
    taken_at: str | None
    author: str | None
    license: str | None
    license_url: str | None
    page_url: str


class SourceAnswerOut(BaseModel):
    id: str
    # ok | no_key | invalid_key | unavailable
    status: str
    count: int


class StreetNear(BaseModel):
    images: list[StreetImageOut]
    sources: list[SourceAnswerOut]


@router.get("/near")
async def near(
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    links: LinksDep,
    transport: MapTransportDep,
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    radius: float = Query(default=street.DEFAULT_RADIUS_M, ge=10, le=street.MOST_RADIUS_M),
    source: str | None = None,
) -> StreetNear:
    """The images of the switched-on sources (`source`: of that one) around the point, nearest
    first. Only the point leaves the server."""
    images, answers = await street.near(
        db, box, account.id, links, lat, lon, radius, transport, only=source
    )
    return StreetNear(
        images=[StreetImageOut(**vars(image)) for image in images],
        sources=[SourceAnswerOut(**vars(answer)) for answer in answers],
    )


@router.get("/image/{source_id}/{image_id}")
async def image(
    source_id: str,
    image_id: ImageId,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    links: LinksDep,
    transport: MapTransportDep,
    size: Literal["thumb", "large"] = "thumb",
) -> Response:
    content, kind = await street.image(
        db, box, account.id, links, source_id, image_id, size, transport
    )
    # The browser keeps it; nothing is stored on the server.
    return Response(content, media_type=kind, headers={"Cache-Control": "private, max-age=86400"})


# "panoramax:<uuid>" or "mapillary:<digits>": an image the card was shown.
StreetKey = Annotated[str, Field(pattern=r"^(panoramax|mapillary):[A-Za-z0-9-]{1,64}$")]


class CompareIn(BaseModel):
    images: list[StreetKey] = Field(min_length=1, max_length=worker_queue.STREET_OTHERS)


class StreetMatchOut(BaseModel):
    """How a street-level image matches the photo (`steward_worker.modules.street`)."""

    key: str
    similarity: float | None
    # Matched point by point (the most alike ones only).
    checked: bool
    matches: int
    inliers: int
    lines: list[tuple[float, float, float, float]]
    # The view of a panorama that matched; the degrees the photo looks to the right of the
    # image, and their spread.
    view: int | None
    offset: float | None
    spread: float | None


class CompareOut(BaseModel):
    # none | queued | running | done | failed
    status: str
    error_code: str | None = None
    # Active workers that run the module now: none, and the comparison waits.
    workers: int
    results: list[StreetMatchOut] = Field(default_factory=list)


async def _comparison(db: DbDep, settings: SettingsDep, asset_id: UUID) -> CompareOut:
    runs = await worker_queue.latest_runs(db, asset_id)
    run = runs.get(worker_queue.STREET_MODULE)
    active = await worker_queue.active_workers(
        db, timedelta(minutes=settings.worker_active_minutes)
    )
    workers = sum(
        1
        for w in active
        if worker_queue.STREET_MODULE in (w.modules or [])
        and worker_queue.STREET_MODULE not in (w.disabled_modules or [])
    )
    if run is None:
        return CompareOut(status="none", workers=workers)
    results = [
        StreetMatchOut(
            key=str(pair.get("other")),
            similarity=pair.get("similarity"),
            checked=bool(pair.get("checked")),
            matches=int(pair.get("matches", 0)),
            inliers=int(pair.get("inliers", 0)),
            lines=[tuple(line) for line in pair.get("lines", [])],
            view=pair.get("view"),
            offset=pair.get("offset"),
            spread=pair.get("spread"),
        )
        for pair in (run.candidates or [])
        if run.status == "done"
    ]
    return CompareOut(
        status=run.status, error_code=run.error_code, workers=workers, results=results
    )


@router.post("/compare/{asset_id}")
async def compare(
    asset_id: UUID,
    body: CompareIn,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
) -> CompareOut:
    """Compares the photo with the street-level images the card shows, on a worker (D-244): the
    images go to it through the core; the photo does not leave the home network."""
    asset = await _own_asset(db, account, asset_id)
    enabled = {s.source.id for s in await street.states(db, account.id) if s.enabled}
    if any(key.partition(":")[0] not in enabled for key in body.images):
        raise ApiError(409, "street_source_off")
    await worker_queue.enqueue_street(db, asset, list(body.images))
    return await _comparison(db, settings, asset.id)


@router.get("/compare/{asset_id}")
async def comparison(
    asset_id: UUID, account: CurrentAccount, db: DbDep, settings: SettingsDep
) -> CompareOut:
    asset = await _own_asset(db, account, asset_id)
    return await _comparison(db, settings, asset.id)
