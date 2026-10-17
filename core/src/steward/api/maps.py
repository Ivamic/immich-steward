# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map settings for the UI and address search (proxied to a Photon geocoder)."""

from typing import Annotated, Any

import httpx2
from fastapi import APIRouter, Query
from pydantic import BaseModel

from steward import __version__
from steward.deps import CurrentAccount, SettingsDep
from steward.errors import ApiError

router = APIRouter()

# Languages supported by the public Photon instance; anything else gets local names.
PHOTON_LANGUAGES = frozenset({"en", "de", "fr"})
GEOCODER_TIMEOUT_S = 10.0
MAX_RESULTS = 8


class MapConfig(BaseModel):
    style_url: str
    geocoder_enabled: bool


class Place(BaseModel):
    name: str
    # Human-readable context: street, city, region, country.
    label: str
    latitude: float
    longitude: float
    kind: str | None


@router.get("/config/map")
async def map_config(settings: SettingsDep, _: CurrentAccount) -> MapConfig:
    return MapConfig(style_url=settings.map_style_url, geocoder_enabled=bool(settings.geocoder_url))


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
