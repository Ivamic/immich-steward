# SPDX-License-Identifier: AGPL-3.0-or-later
"""Street-level images near a point (`steward.street`, D-244): the sources of the account, the
images near a point and their previews, all through the core."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic import BaseModel, Field

from steward import street
from steward.api.maps import MapTransportDep
from steward.deps import CurrentAccount, DbDep, SecretBoxDep

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
