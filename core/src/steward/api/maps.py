# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map settings for the UI, its satellite imagery sources and address search (proxied to a
Photon geocoder)."""

from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlsplit

import httpx2
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from steward import __version__, map_sources
from steward.deps import CurrentAccount, DbDep, SecretBoxDep, SettingsDep
from steward.errors import ApiError

router = APIRouter()

# Languages supported by the public Photon instance; anything else gets local names.
PHOTON_LANGUAGES = frozenset({"en", "de", "fr"})
GEOCODER_TIMEOUT_S = 10.0
MAX_RESULTS = 8


class MapVariant(BaseModel):
    id: str
    # With the account's key; null while the source is off.
    tiles: str | None
    attribution: str


class MapSourceConfig(BaseModel):
    """A satellite source for the map of the account. Only a source that is on carries tile
    addresses (with the account's own key, D-141)."""

    id: str
    name: str
    enabled: bool
    # "no_key", "invalid", "exhausted" or "ok" (`map_sources.State.status`).
    status: str
    variants: list[MapVariant]
    tile_size: int
    max_zoom: int
    logo_url: str | None
    copyright: str | None
    copyright_url: str | None


class AutoOut(BaseModel):
    far: str | None
    near: str | None
    switch_zoom: int = Field(ge=1, le=22)


class MapConfig(BaseModel):
    style_url: str
    # For the dark theme of the web UI; null: `style_url`, dimmed.
    style_url_dark: str | None
    geocoder_enabled: bool
    sources: list[MapSourceConfig]
    auto: AutoOut


class Place(BaseModel):
    name: str
    # Human-readable context: street, city, region, country.
    label: str
    latitude: float
    longitude: float
    kind: str | None


@router.get("/config/map")
async def map_config(
    settings: SettingsDep, account: CurrentAccount, db: DbDep, box: SecretBoxDep
) -> MapConfig:
    states = await map_sources.states(db, box, account.id)
    auto = await map_sources.get_auto(db, account.id, states)
    return MapConfig(
        style_url=settings.map_style_url,
        style_url_dark=settings.map_style_url_dark or None,
        geocoder_enabled=bool(settings.geocoder_url),
        sources=[_source_config(state) for state in states],
        auto=AutoOut(**vars(auto)),
    )


def _source_config(state: map_sources.State) -> MapSourceConfig:
    src, on = state.source, state.enabled
    key = state.api_key if on else None
    return MapSourceConfig(
        id=src.id,
        name=src.name,
        enabled=on,
        status=state.status,
        variants=[
            MapVariant(
                id=v.id,
                tiles=map_sources.fill(v.tiles, key) if on else None,
                attribution=v.attribution,
            )
            for v in src.variants
        ],
        tile_size=src.tile_size,
        max_zoom=src.max_zoom,
        logo_url=src.logo_url,
        copyright=src.copyright,
        copyright_url=map_sources.fill(src.copyright_url, key)
        if on and src.copyright_url
        else None,
    )


def get_map_transport(request: Request) -> httpx2.AsyncBaseTransport | None:
    transport: httpx2.AsyncBaseTransport | None = request.app.state.map_transport
    return transport


MapTransportDep = Annotated[httpx2.AsyncBaseTransport | None, Depends(get_map_transport)]


class ProviderUsageOut(BaseModel):
    used: int | None
    estimated: int | None
    since: str | None
    until: str | None
    fetched_at: datetime
    error: str | None


class MapSourceItem(BaseModel):
    """A source in the settings of the account. Keys only masked: they never come back whole."""

    id: str
    name: str
    needs_key: bool
    enabled: bool
    status: str
    key: str | None
    key_problem_at: datetime | None
    # Whether the provider's usage can be read with a token, and the token, masked.
    usage_token_supported: bool
    usage_token: str | None
    provider_usage: ProviderUsageOut | None
    # The own count: tiles loaded by this account since then (D-146).
    tiles: int
    counted_since: datetime
    reset_day: int | None
    free_quota: int | None
    noncommercial: bool
    years: list[int]
    terms_url: str
    site_url: str
    key_url: str | None
    # After a save or a check: "unreachable" when the provider could not be asked.
    key_check: str | None = None


class MapSources(BaseModel):
    sources: list[MapSourceItem]
    auto: AutoOut


def _item(state: map_sources.State, key_check: str | None = None) -> MapSourceItem:
    src, usage = state.source, state.provider_usage
    return MapSourceItem(
        id=src.id,
        name=src.name,
        needs_key=src.needs_key,
        enabled=state.enabled,
        status=state.status,
        key=map_sources.mask(state.api_key),
        key_problem_at=state.key_problem_at,
        usage_token_supported=src.usage_token,
        usage_token=map_sources.mask(state.usage_token),
        provider_usage=ProviderUsageOut(**vars(usage)) if usage else None,
        tiles=state.tiles,
        counted_since=state.counted_since,
        reset_day=state.reset_day,
        free_quota=src.free_quota,
        noncommercial=src.noncommercial,
        years=list(src.years),
        terms_url=src.terms_url,
        site_url=src.site_url,
        key_url=src.key_url,
        key_check=key_check,
    )


async def _one(
    db: DbDep, box: SecretBoxDep, account: CurrentAccount, source_id: str, key_check: str | None
) -> MapSourceItem:
    states = await map_sources.states(db, box, account.id)
    return _item(next(s for s in states if s.source.id == source_id), key_check)


@router.get("/map-sources")
async def get_map_sources(
    account: CurrentAccount, db: DbDep, box: SecretBoxDep, transport: MapTransportDep
) -> MapSources:
    """The sources in the settings; the provider's usage is asked again when it is old."""
    await map_sources.refresh_provider_usage(db, box, account.id, transport=transport)
    states = await map_sources.states(db, box, account.id)
    auto = await map_sources.get_auto(db, account.id, states)
    return MapSources(sources=[_item(s) for s in states], auto=AutoOut(**vars(auto)))


@router.put("/map-sources/auto")
async def set_map_auto(
    body: AutoOut, account: CurrentAccount, db: DbDep, box: SecretBoxDep
) -> AutoOut:
    auto = map_sources.Auto(body.far, body.near, body.switch_zoom)
    return AutoOut(**vars(await map_sources.save_auto(db, box, account.id, auto)))


class TileReport(BaseModel):
    """Tiles the browser loaded since its last report, and key problems it saw, per source."""

    tiles: dict[str, int] = {}
    problems: dict[str, str] = {}


@router.post("/map-sources/report", status_code=204)
async def report_map_tiles(body: TileReport, account: CurrentAccount, db: DbDep) -> Response:
    await map_sources.report(db, account.id, body.tiles, body.problems)
    return Response(status_code=204)


def _site(request: Request) -> str | None:
    """The address of the app in the browser (scheme, host, port), from which the settings were
    saved: a key restricted to it is checked as from there."""
    origin = request.headers.get("origin")
    if origin and origin != "null":
        return origin.rstrip("/")
    referer = urlsplit(request.headers.get("referer", ""))
    return f"{referer.scheme}://{referer.netloc}" if referer.scheme and referer.netloc else None


class MapSourceUpdate(BaseModel):
    """Only the fields that are given change; an empty or null key or token deletes it."""

    enabled: bool | None = None
    api_key: str | None = Field(default=None, max_length=1000)
    usage_token: str | None = Field(default=None, max_length=1000)
    reset_day: int | None = None


@router.put("/map-sources/{source_id}")
async def update_map_source(
    source_id: str,
    body: MapSourceUpdate,
    request: Request,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    transport: MapTransportDep,
) -> MapSourceItem:
    """A new key is checked with the provider at once (the tiles of Esri take any key)."""
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    if "enabled" in fields and fields["enabled"] is None:
        raise ApiError(422, "map_source_enabled_invalid")
    site = _site(request)
    check = await map_sources.update(
        db, box, account.id, source_id, transport=transport, site=site, **fields
    )
    return await _one(db, box, account, source_id, check)


@router.post("/map-sources/{source_id}/check")
async def check_map_key(
    source_id: str,
    request: Request,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    transport: MapTransportDep,
) -> MapSourceItem:
    check = await map_sources.check_key(db, box, account.id, source_id, transport, _site(request))
    return await _one(db, box, account, source_id, check)


@router.post("/map-sources/{source_id}/reset-count")
async def reset_map_count(
    source_id: str, account: CurrentAccount, db: DbDep, box: SecretBoxDep
) -> MapSourceItem:
    await map_sources.reset_count(db, account.id, source_id)
    return await _one(db, box, account, source_id, None)


@router.post("/map-sources/{source_id}/refresh-usage")
async def refresh_map_usage(
    source_id: str,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    transport: MapTransportDep,
) -> MapSourceItem:
    map_sources.source(source_id)
    await map_sources.refresh_provider_usage(db, box, account.id, force=True, transport=transport)
    return await _one(db, box, account, source_id, None)


@router.get("/geocode")
async def geocode(
    settings: SettingsDep,
    _: CurrentAccount,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    lang: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> list[Place]:
    if not settings.geocoder_url:
        raise ApiError(503, "geocoder_disabled")
    params: dict[str, Any] = {"q": q, "limit": MAX_RESULTS}
    if lang in PHOTON_LANGUAGES:
        params["lang"] = lang
    if lat is not None and lon is not None:  # prefer results near the current map view
        params |= {"lat": lat, "lon": lon}
    headers = {"User-Agent": f"immich-steward/{__version__}"}
    try:
        async with httpx2.AsyncClient(timeout=GEOCODER_TIMEOUT_S, headers=headers) as http:
            response = await http.get(settings.geocoder_url.rstrip("/") + "/api", params=params)
            response.raise_for_status()
    except httpx2.HTTPError as exc:
        raise ApiError(502, "geocoder_unavailable") from exc
    return [_place(feature) for feature in response.json().get("features", [])]


def _place(feature: dict[str, Any]) -> Place:
    props = feature.get("properties", {})
    longitude, latitude = feature["geometry"]["coordinates"]
    name = props.get("name") or props.get("street") or props.get("city") or ""
    street = " ".join(filter(None, [props.get("street"), props.get("housenumber")]))
    parts = [street, props.get("city"), props.get("state"), props.get("country")]
    label = ", ".join(dict.fromkeys(p for p in parts if p and p != name))
    return Place(
        name=name,
        label=label,
        latitude=latitude,
        longitude=longitude,
        kind=props.get("osm_value"),
    )
