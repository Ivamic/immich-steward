# SPDX-License-Identifier: AGPL-3.0-or-later
"""Street-level images near a point (0.14, D-244): Mapillary and Panoramax, for the user to
compare with a photo by eye.

Only the coordinates of the point the user looks at leave the server, and only while the user
has a source switched on and the images shown in the card. The images are fetched through the
core (the providers see the server, not the browser) and never stored: the links of a search are
kept in memory for a while, so that the previews of what the browser was just shown can be
fetched by their id alone.
"""

import asyncio
import logging
import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward import __version__
from steward.crypto import SecretBox
from steward.errors import ApiError
from steward.models import StreetSourceSetting

log = logging.getLogger(__name__)

Size = Literal["thumb", "large"]
# `key_problem`: the provider refused the token.
KEY_PROBLEMS = ("invalid",)

PANORAMAX_SEARCH = "https://api.panoramax.xyz/api/search"
MAPILLARY_GRAPH = "https://graph.mapillary.com"
# The points of a search; the previews are asked for the nearest only.
MAPILLARY_FIELDS = (
    "id,geometry,computed_geometry,compass_angle,computed_compass_angle,captured_at,creator,"
    "is_pano,camera_type"
)
# The most images a search of Mapillary gives.
MAPILLARY_POINTS_MOST = 2000
# Mapillary allows a bounding box below 0.01 square degrees (2026-01); 300 m is about 0.006.
MOST_RADIUS_M = 300
DEFAULT_RADIUS_M = 100
# Images a search asks each provider for, and how many nearest it returns.
ASK_EACH = 100
NEAR_MOST = 40
TIMEOUT_S = 15.0
# The federated catalog of Panoramax answers in half a second, or in 20-30 s when busy
# (2026-11-24): not waited for that long.
PANORAMAX_TIMEOUT_S = 10.0
# Previews: what the browser was shown stays fetchable this long; no more than this many links.
LINKS_FOR_S = 3600.0
LINKS_MOST = 20_000
# A preview larger than this is not passed on.
IMAGE_MOST_BYTES = 8 * 1024 * 1024
EARTH_M = 6_371_000.0


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    needs_key: bool
    site_url: str
    terms_url: str
    key_url: str | None = None


SOURCES: tuple[Source, ...] = (
    Source(
        id="panoramax",
        name="Panoramax",
        needs_key=False,
        site_url="https://panoramax.fr/",
        terms_url="https://docs.panoramax.fr/",
    ),
    Source(
        id="mapillary",
        name="Mapillary",
        needs_key=True,
        site_url="https://www.mapillary.com/",
        terms_url="https://www.mapillary.com/terms",
        key_url="https://www.mapillary.com/dashboard/developers",
    ),
)
BY_ID = {s.id: s for s in SOURCES}


def source(source_id: str) -> Source:
    found = BY_ID.get(source_id)
    if found is None:
        raise ApiError(404, "street_source_not_found")
    return found


@dataclass
class StreetImage:
    source: str
    id: str
    latitude: float
    longitude: float
    distance_m: float
    # Degrees clockwise from north the camera looked (None: unknown).
    heading: float | None
    # A 360-degree panorama (equirectangular).
    pano: bool
    taken_at: str | None
    author: str | None
    license: str | None
    license_url: str | None
    page_url: str


@dataclass
class SourceState:
    source: Source
    enabled: bool
    has_key: bool
    key_problem: str | None


@dataclass
class SourceAnswer:
    """How a source answered a search: `ok`, `no_key`, `invalid_key` or `unavailable`."""

    id: str
    status: str
    count: int = 0


async def states(db: AsyncSession, account_id: UUID) -> list[SourceState]:
    rows = {
        row.source_id: row
        for row in await db.scalars(
            select(StreetSourceSetting).where(StreetSourceSetting.account_id == account_id)
        )
    }
    return [
        SourceState(
            source=s,
            enabled=bool(rows[s.id].enabled) if s.id in rows else False,
            has_key=s.id in rows and rows[s.id].api_key_encrypted is not None,
            key_problem=rows[s.id].key_problem if s.id in rows else None,
        )
        for s in SOURCES
    ]


async def update(
    db: AsyncSession,
    box: SecretBox,
    account_id: UUID,
    source_id: str,
    *,
    enabled: bool | None = None,
    api_key: str | None = None,
    key_given: bool = False,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> None:
    """Switches a source on or off and keeps its token (an empty one deletes it); a new token is
    checked with the provider at once."""
    found = source(source_id)
    row = await db.get(StreetSourceSetting, (account_id, source_id))
    if row is None:
        row = StreetSourceSetting(account_id=account_id, source_id=source_id, enabled=False)
        db.add(row)
    if enabled is not None:
        row.enabled = enabled
    if key_given and found.needs_key:
        key = (api_key or "").strip()
        row.api_key_encrypted = box.encrypt(key) if key else None
        row.key_problem = None
        if key:
            row.key_problem = await _check_key(key, transport)
    await db.commit()


async def _check_key(key: str, transport: httpx2.AsyncBaseTransport | None) -> str | None:
    """None when Mapillary takes the token; "invalid" when it refuses it. Unreachable: not known,
    so not marked."""
    params = {"bbox": "0.0,0.0,0.0001,0.0001", "limit": "1", "fields": "id"}
    try:
        async with _client(transport) as http:
            answer = await http.get(
                f"{MAPILLARY_GRAPH}/images",
                params=params,
                headers={"Authorization": f"OAuth {key}"},
            )
    except httpx2.HTTPError:
        return None
    return "invalid" if answer.status_code in (400, 401, 403) else None


def _client(transport: httpx2.AsyncBaseTransport | None) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        timeout=TIMEOUT_S,
        headers={"User-Agent": f"immich-steward/{__version__}"},
        transport=transport,
        follow_redirects=True,
    )


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_M * math.asin(math.sqrt(a))


def bbox(latitude: float, longitude: float, radius_m: float) -> tuple[float, float, float, float]:
    """West, south, east, north of the square around the point."""
    dlat = math.degrees(radius_m / EARTH_M)
    dlon = dlat / max(math.cos(math.radians(latitude)), 0.01)
    return (longitude - dlon, latitude - dlat, longitude + dlon, latitude + dlat)


class Links:
    """Where the previews of recently shown images are, by (account, source, id)."""

    def __init__(self) -> None:
        self._links: OrderedDict[tuple[UUID, str, str], tuple[float, dict[str, str]]] = (
            OrderedDict()
        )

    def keep(self, account_id: UUID, source_id: str, image_id: str, urls: dict[str, str]) -> None:
        key = (account_id, source_id, image_id)
        self._links[key] = (time.monotonic() + LINKS_FOR_S, urls)
        self._links.move_to_end(key)
        while len(self._links) > LINKS_MOST:
            self._links.popitem(last=False)

    def get(self, account_id: UUID, source_id: str, image_id: str) -> dict[str, str] | None:
        found = self._links.get((account_id, source_id, image_id))
        if found is None or found[0] < time.monotonic():
            return None
        return found[1]


async def near(
    db: AsyncSession,
    box: SecretBox,
    account_id: UUID,
    links: Links,
    latitude: float,
    longitude: float,
    radius_m: float = DEFAULT_RADIUS_M,
    transport: httpx2.AsyncBaseTransport | None = None,
    only: str | None = None,
) -> tuple[list[StreetImage], list[SourceAnswer]]:
    """The images of the switched-on sources (`only`: of that one) within `radius_m` of the
    point, nearest first. The sources are asked at the same time: a slow one holds up only its
    own answer."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ApiError(422, "street_point_invalid")
    if only is not None:
        source(only)
    radius_m = min(max(radius_m, 10.0), MOST_RADIUS_M)
    rows = {
        row.source_id: row
        for row in await db.scalars(
            select(StreetSourceSetting).where(
                StreetSourceSetting.account_id == account_id,
                StreetSourceSetting.enabled.is_(True),
            )
        )
    }
    asked = [s for s in SOURCES if s.id in rows and (only is None or s.id == only)]

    async def ask(
        http: httpx2.AsyncClient, s: Source
    ) -> tuple[SourceAnswer, list[tuple[StreetImage, dict[str, str]]]]:
        row = rows[s.id]
        key = box.decrypt(row.api_key_encrypted) if row.api_key_encrypted else None
        if s.needs_key and not key:
            return SourceAnswer(s.id, "no_key"), []
        try:
            if s.id == "panoramax":
                images = await _panoramax(http, latitude, longitude, radius_m)
            else:
                assert key is not None
                images = await _mapillary(http, key, latitude, longitude, radius_m)
        except _Refused:
            row.key_problem = "invalid"
            return SourceAnswer(s.id, "invalid_key"), []
        except (httpx2.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("street-level images: %s did not answer: %r", s.id, exc)
            return SourceAnswer(s.id, "unavailable"), []
        if s.needs_key and row.key_problem:
            row.key_problem = None
        inside = [(i, u) for i, u in images if i.distance_m <= radius_m]
        return SourceAnswer(s.id, "ok", len(inside)), inside

    async with _client(transport) as http:
        results = await asyncio.gather(*(ask(http, s) for s in asked))
    await db.commit()
    found = sorted(
        (pair for _, images in results for pair in images), key=lambda pair: pair[0].distance_m
    )[:NEAR_MOST]
    for image, urls in found:
        links.keep(account_id, image.source, image.id, urls)
    return [image for image, _ in found], [answer for answer, _ in results]


class _Refused(Exception):
    """The provider refused the token."""


async def _panoramax(
    http: httpx2.AsyncClient, latitude: float, longitude: float, radius_m: float
) -> list[tuple[StreetImage, dict[str, str]]]:
    """The images in the square around the point. The catalog gives the first `ASK_EACH` of a
    square, not the nearest: when it gives that many, the four quarters are asked too, so that
    a busy street on one side does not hide the rest."""
    west, south, east, north = bbox(latitude, longitude, radius_m)

    async def square(w: float, s: float, e: float, n: float) -> list[dict[str, Any]]:
        answer = await http.get(
            PANORAMAX_SEARCH,
            params={"bbox": f"{w:.6f},{s:.6f},{e:.6f},{n:.6f}", "limit": str(ASK_EACH)},
            timeout=PANORAMAX_TIMEOUT_S,
        )
        answer.raise_for_status()
        features: list[dict[str, Any]] = answer.json().get("features", [])
        return features

    features = await square(west, south, east, north)
    if len(features) >= ASK_EACH:
        mid_lon, mid_lat = (west + east) / 2, (south + north) / 2
        quarters = await asyncio.gather(
            square(west, south, mid_lon, mid_lat),
            square(mid_lon, south, east, mid_lat),
            square(west, mid_lat, mid_lon, north),
            square(mid_lon, mid_lat, east, north),
            return_exceptions=True,
        )
        for quarter in quarters:
            if isinstance(quarter, list):
                features += quarter
    seen: set[str] = set()
    found = []
    for feature in features:
        image_id = str(feature.get("id"))
        if image_id in seen:
            continue
        seen.add(image_id)
        try:
            found.append(_panoramax_image(feature, latitude, longitude))
        except (KeyError, TypeError, ValueError, IndexError):
            continue  # an image without a point or a preview
    return found


def _panoramax_image(
    feature: dict[str, Any], latitude: float, longitude: float
) -> tuple[StreetImage, dict[str, str]]:
    lon, lat = feature["geometry"]["coordinates"][:2]
    props = feature.get("properties", {})
    assets = feature["assets"]
    view = props.get("pers:interior_orientation") or {}
    producers = [
        p.get("name")
        for p in feature.get("providers", [])
        if "producer" in (p.get("roles") or []) and p.get("name")
    ]
    license_link = next(
        (link.get("href") for link in feature.get("links", []) if link.get("rel") == "license"),
        None,
    )
    heading = props.get("view:azimuth")
    image = StreetImage(
        source="panoramax",
        id=str(feature["id"]),
        latitude=float(lat),
        longitude=float(lon),
        distance_m=distance_m(latitude, longitude, float(lat), float(lon)),
        heading=float(heading) if heading is not None else None,
        pano=view.get("field_of_view") == 360,
        taken_at=props.get("datetime"),
        author=props.get("geovisio:producer") or (producers[0] if producers else None),
        license=props.get("license"),
        license_url=license_link,
        page_url=f"https://api.panoramax.xyz/#focus=pic&pic={feature['id']}",
    )
    large = assets.get("sd") or assets["thumb"]
    return image, {"thumb": assets["thumb"]["href"], "large": large["href"]}


async def _mapillary(
    http: httpx2.AsyncClient, key: str, latitude: float, longitude: float, radius_m: float
) -> list[tuple[StreetImage, dict[str, str]]]:
    """The images in the square around the point: their points first (up to the most a search
    gives, not the first hundred, which lie anywhere in the square), then the previews of the
    nearest ones only."""
    west, south, east, north = bbox(latitude, longitude, radius_m)
    headers = {"Authorization": f"OAuth {key}"}
    answer = await http.get(
        f"{MAPILLARY_GRAPH}/images",
        params={
            "bbox": f"{west:.6f},{south:.6f},{east:.6f},{north:.6f}",
            "limit": str(MAPILLARY_POINTS_MOST),
            "fields": MAPILLARY_FIELDS,
        },
        headers=headers,
    )
    if answer.status_code in (401, 403):
        raise _Refused
    answer.raise_for_status()
    images = []
    for item in answer.json().get("data", []):
        try:
            images.append(_mapillary_image(item, latitude, longitude))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    nearest = sorted(images, key=lambda image: image.distance_m)[:NEAR_MOST]
    if not nearest:
        return []
    previews = await http.get(
        MAPILLARY_GRAPH,
        params={"ids": ",".join(i.id for i in nearest), "fields": "thumb_512_url,thumb_2048_url"},
        headers=headers,
    )
    previews.raise_for_status()
    urls: dict[str, Any] = previews.json()
    return [
        (
            image,
            {
                "thumb": urls[image.id]["thumb_512_url"],
                "large": urls[image.id].get("thumb_2048_url") or urls[image.id]["thumb_512_url"],
            },
        )
        for image in nearest
        if (urls.get(image.id) or {}).get("thumb_512_url")
    ]


def _mapillary_image(item: dict[str, Any], latitude: float, longitude: float) -> StreetImage:
    lon, lat = (item.get("computed_geometry") or item["geometry"])["coordinates"][:2]
    heading = item.get("computed_compass_angle", item.get("compass_angle"))
    taken = item.get("captured_at")
    return StreetImage(
        source="mapillary",
        id=str(item["id"]),
        latitude=float(lat),
        longitude=float(lon),
        distance_m=distance_m(latitude, longitude, float(lat), float(lon)),
        heading=float(heading) % 360 if heading is not None else None,
        pano=bool(item.get("is_pano"))
        or item.get("camera_type") in ("equirectangular", "spherical"),
        taken_at=(
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(taken) / 1000)) if taken else None
        ),
        author=(item.get("creator") or {}).get("username"),
        # Mapillary's terms: the images of others are CC BY-SA 4.0.
        license="CC-BY-SA-4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        page_url=f"https://www.mapillary.com/app/?pKey={item['id']}",
    )


async def image(
    db: AsyncSession,
    box: SecretBox,
    account_id: UUID,
    links: Links,
    source_id: str,
    image_id: str,
    size: Size,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> tuple[bytes, str]:
    """A preview of an image the account was shown: its bytes and type. The address comes from
    the provider's answer, never from the browser."""
    found = source(source_id)
    row = await db.get(StreetSourceSetting, (account_id, source_id))
    if row is None or not row.enabled:
        raise ApiError(404, "street_image_not_found")
    urls = links.get(account_id, source_id, image_id)
    async with _client(transport) as http:
        if urls is None:
            # Shown before a restart of the core: asked from the provider by its id.
            key = box.decrypt(row.api_key_encrypted) if row.api_key_encrypted else None
            urls = await _lookup(http, found, key, image_id)
            if urls is None:
                raise ApiError(404, "street_image_not_found")
            links.keep(account_id, source_id, image_id, urls)
        url = urls[size]
        if not url.startswith("https://"):
            raise ApiError(404, "street_image_not_found")
        try:
            answer = await http.get(url)
        except httpx2.HTTPError as exc:
            raise ApiError(502, "street_unavailable") from exc
    kind = answer.headers.get("content-type", "").split(";")[0].strip()
    if answer.status_code != 200 or not kind.startswith("image/"):
        raise ApiError(502, "street_unavailable")
    if len(answer.content) > IMAGE_MOST_BYTES:
        raise ApiError(502, "street_unavailable")
    return answer.content, kind


async def _lookup(
    http: httpx2.AsyncClient, found: Source, key: str | None, image_id: str
) -> dict[str, str] | None:
    try:
        if found.id == "panoramax":
            answer = await http.get(PANORAMAX_SEARCH, params={"ids": image_id})
            answer.raise_for_status()
            features = answer.json().get("features", [])
            if not features or not features[0].get("assets", {}).get("thumb"):
                return None
            assets = features[0]["assets"]
            return {
                "thumb": assets["thumb"]["href"],
                "large": (assets.get("sd") or assets["thumb"])["href"],
            }
        if not key or not image_id.isdigit():
            return None
        answer = await http.get(
            f"{MAPILLARY_GRAPH}/{image_id}",
            params={"fields": "thumb_512_url,thumb_2048_url"},
            headers={"Authorization": f"OAuth {key}"},
        )
        answer.raise_for_status()
        item = answer.json()
        if not item.get("thumb_512_url"):
            return None
        return {
            "thumb": item["thumb_512_url"],
            "large": item.get("thumb_2048_url") or item["thumb_512_url"],
        }
    except (httpx2.HTTPError, ValueError, KeyError, TypeError):
        return None
