# SPDX-License-Identifier: AGPL-3.0-or-later
"""Satellite imagery sources of the map, per account (D-140...D-147).

Only addresses and rules live here: the browser loads the tiles straight from the provider, with
no proxy and no cache in the core (provider terms). A source stays off until the account switches
it on, which is also its consent to the provider's terms; a source with a key needs the account's
own key. The core counts the tiles the browsers report ("used by us": the same key may serve other
apps too) and reads the provider's own usage where there is a way to (MapTiler, with a token).
"""

import calendar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx2
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from steward import __version__
from steward.crypto import SecretBox
from steward.errors import ApiError
from steward.models import MapAuto, MapSourceSetting, MapTileUsage, utcnow

# What is wrong with the key: the provider does not accept it (wrong, revoked; MapTiler answers so
# also when the limit is reached), or it closed the access (the limit, most likely).
INVALID = "invalid"
EXHAUSTED = "exhausted"
KEY_PROBLEMS = (INVALID, EXHAUSTED)

# The near source starts at this zoom: at the latitude of the Balkans z14 is ~7 m per pixel, where
# the 10 m Sentinel-2 is only blurred.
DEFAULT_SWITCH_ZOOM = 14
# The provider's usage is asked again after this long (its data are per day anyway).
PROVIDER_USAGE_TTL = timedelta(hours=3)
PROVIDER_TIMEOUT_S = 10.0
# One report of the browser covers half a minute at most; more tiles is a broken client.
MAX_REPORTED_TILES = 100_000


@dataclass(frozen=True)
class Variant:
    """One layer of a source: a year of EOX, the only one of the others."""

    id: str
    # `{z}`, `{x}`, `{y}` for MapLibre, `{key}` for the account's key.
    tiles: str
    # HTML; `{copyright}` stands for the provider's copyright text (`Source.copyright`).
    attribution: str


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    needs_key: bool
    # The first is the default.
    variants: tuple[Variant, ...]
    tile_size: int
    # The deepest zoom with real data; MapLibre stretches it further instead of loading more.
    max_zoom: int
    terms_url: str
    site_url: str
    # Where the account gets a key.
    key_url: str | None = None
    # Where the account sees the provider's own count of its usage and the limits.
    usage_url: str | None = None
    # Tiles (requests) a month on the free plan, to put the provider's usage against.
    free_quota: int | None = None
    # The free use allows no commercial use.
    noncommercial: bool = False
    logo_url: str | None = None
    # The copyright text, also the fallback when the browser cannot read `copyright_url`.
    copyright: str | None = None
    # JSON with `copyrightText`, read by the browser (it changes: Maxar became Vantor).
    copyright_url: str | None = None
    # A cheap request that tells whether the key is accepted (the tiles of Esri take any key).
    key_check_url: str | None = None
    # The provider's usage can be read with a token of the account (MapTiler service token).
    usage_token: bool = False
    years: tuple[int, ...] = field(default=())


EOX_YEARS = tuple(range(2025, 2015, -1))
EOX_COPERNICUS = {2016: "2016 &amp; 2017"}


def _eox_variant(year: int) -> Variant:
    # The 2016 layer has no year in its name.
    layer = "s2cloudless_3857" if year == 2016 else f"s2cloudless-{year}_3857"
    return Variant(
        id=str(year),
        tiles=f"https://tiles.maps.eox.at/wmts/1.0.0/{layer}/default/g/{{z}}/{{y}}/{{x}}.jpg",
        attribution=(
            '<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless'
            ' - https://s2maps.eu</a> by <a href="https://eox.at" target="_blank"'
            ' rel="noopener">EOX IT Services GmbH</a> (Contains modified Copernicus Sentinel data'
            f" {EOX_COPERNICUS.get(year, str(year))})"
        ),
    )


ESRI_IMAGERY = "https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer"
MAPTILER_SATELLITE = "https://api.maptiler.com/tiles/satellite-v2"

SOURCES: tuple[Source, ...] = (
    Source(
        id="eox",
        name="Sentinel-2 cloudless (EOX)",
        needs_key=False,
        variants=tuple(_eox_variant(year) for year in EOX_YEARS),
        tile_size=256,
        max_zoom=14,
        terms_url="https://s2maps.eu/",
        site_url="https://s2maps.eu/",
        noncommercial=True,
        years=EOX_YEARS,
    ),
    Source(
        id="esri",
        name="Esri World Imagery",
        needs_key=True,
        variants=(
            Variant(
                id="default",
                # Esri's order is {y}/{x}.
                tiles=ESRI_IMAGERY + "/tile/{z}/{y}/{x}?token={key}",
                attribution=(
                    'Powered by <a href="https://www.esri.com" target="_blank"'
                    ' rel="noopener">Esri</a> | {copyright}'
                ),
            ),
        ),
        tile_size=256,
        max_zoom=19,
        terms_url="https://www.esri.com/en-us/legal/terms/full-master-agreement",
        site_url="https://location.arcgis.com/",
        key_url="https://location.arcgis.com/",
        usage_url="https://location.arcgis.com/usage/",
        free_quota=2_000_000,
        copyright=(
            "Source: Esri, Vantor, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS,"
            " AeroGRID, IGN, and the GIS User Community"
        ),
        copyright_url=ESRI_IMAGERY + "?f=json&token={key}",
        key_check_url=(
            "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles"
            "/arcgis/imagery?token={key}"
        ),
    ),
    Source(
        id="maptiler",
        name="MapTiler Satellite",
        needs_key=True,
        variants=(
            Variant(
                id="default",
                tiles=MAPTILER_SATELLITE + "/{z}/{x}/{y}.jpg?key={key}",
                attribution=(
                    '<a href="https://www.maptiler.com/copyright/" target="_blank"'
                    ' rel="noopener">&copy; MapTiler</a> <a'
                    ' href="https://www.openstreetmap.org/copyright" target="_blank"'
                    ' rel="noopener">&copy; OpenStreetMap contributors</a>'
                ),
            ),
        ),
        tile_size=256,
        max_zoom=20,
        terms_url="https://www.maptiler.com/cloud/terms/",
        site_url="https://www.maptiler.com/",
        key_url="https://cloud.maptiler.com/account/keys/",
        usage_url="https://cloud.maptiler.com/account/analytics",
        free_quota=100_000,
        noncommercial=True,
        # On the free plan the logo must be on the map; loaded from MapTiler with its tiles.
        logo_url="https://api.maptiler.com/resources/logo.svg",
        key_check_url=MAPTILER_SATELLITE + "/tiles.json?key={key}",
        usage_token=True,
    ),
)
BY_ID = {source.id: source for source in SOURCES}
# Auto switching takes the next of these that is usable when one is not.
NEAR_ORDER = ("esri", "maptiler", "eox")


def source(source_id: str) -> Source:
    if source_id not in BY_ID:
        raise ApiError(404, "map_source_not_found")
    return BY_ID[source_id]


def fill(template: str, key: str | None) -> str:
    return template.replace("{key}", quote(key or "", safe=""))


def mask(secret: str | None) -> str | None:
    """Enough of a key to tell which one it is, not enough to use it."""
    if not secret:
        return None
    return "••••" + secret[-4:] if len(secret) > 8 else "••••"


@dataclass(frozen=True)
class ProviderUsage:
    """What the provider says the key used in its current period."""

    used: int | None
    # The provider's estimate for the whole period.
    estimated: int | None
    since: str | None
    until: str | None
    fetched_at: str
    # "token_invalid" or "unreachable"; then the numbers are those of the last good answer.
    error: str | None = None


@dataclass
class State:
    """A source as an account has it."""

    source: Source
    enabled: bool
    api_key: str | None
    usage_token: str | None
    counted_since: datetime
    reset_day: int | None
    key_problem: str | None
    key_problem_at: datetime | None
    tiles: int
    provider_usage: ProviderUsage | None

    @property
    def usable(self) -> bool:
        """Can be shown on the map: on, with a key where needed, and no known problem."""
        has_key = bool(self.api_key) or not self.source.needs_key
        return self.enabled and has_key and self.key_problem is None

    @property
    def status(self) -> str:
        if self.source.needs_key and not self.api_key:
            return "no_key"
        return self.key_problem or "ok"


def period_start(today: date, reset_day: int) -> date:
    """The last day on or before `today` that a monthly period starting on `reset_day` began;
    short months start on their last day."""

    def start_in(year: int, month: int) -> date:
        return date(year, month, min(reset_day, calendar.monthrange(year, month)[1]))

    start = start_in(today.year, today.month)
    if start <= today:
        return start
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return start_in(year, month)


async def _rows(db: AsyncSession, account_id: UUID) -> dict[str, MapSourceSetting]:
    rows = await db.scalars(
        select(MapSourceSetting).where(MapSourceSetting.account_id == account_id)
    )
    return {row.source_id: row for row in rows if row.source_id in BY_ID}


def _row(rows: dict[str, MapSourceSetting], account_id: UUID, source_id: str) -> MapSourceSetting:
    row = rows.get(source_id)
    if row is None:
        row = MapSourceSetting(
            account_id=account_id, source_id=source_id, enabled=False, counted_since=utcnow()
        )
        rows[source_id] = row
    return row


async def _reset_count(db: AsyncSession, row: MapSourceSetting, since: datetime) -> None:
    await db.execute(
        delete(MapTileUsage).where(
            MapTileUsage.account_id == row.account_id, MapTileUsage.source_id == row.source_id
        )
    )
    row.counted_since = since
    # A new period of the provider: the limit is back.
    if row.key_problem == EXHAUSTED:
        row.key_problem = row.key_problem_at = None


async def _roll_periods(db: AsyncSession, rows: dict[str, MapSourceSetting]) -> bool:
    """Starts the own count anew where the provider's monthly period changed since."""
    now = utcnow()
    changed = False
    for row in rows.values():
        if row.reset_day is None:
            continue
        start = datetime.combine(period_start(now.date(), row.reset_day), time(), UTC)
        if row.counted_since < start:
            await _reset_count(db, row, start)
            changed = True
    return changed


async def states(db: AsyncSession, box: SecretBox, account_id: UUID) -> list[State]:
    """Every source, in the order of the catalog, as this account has it."""
    rows = await _rows(db, account_id)
    if await _roll_periods(db, rows):
        await db.commit()
    result = await db.execute(
        select(MapTileUsage.source_id, func.sum(MapTileUsage.tiles))
        .where(MapTileUsage.account_id == account_id)
        .group_by(MapTileUsage.source_id)
    )
    counts = {source_id: total for source_id, total in result}

    def state(src: Source) -> State:
        row = rows.get(src.id)
        if row is None:
            return State(src, False, None, None, utcnow(), None, None, None, 0, None)
        usage = ProviderUsage(**row.provider_usage) if row.provider_usage else None
        return State(
            source=src,
            enabled=row.enabled,
            api_key=_decrypt(box, row.api_key_encrypted),
            usage_token=_decrypt(box, row.usage_token_encrypted),
            counted_since=row.counted_since,
            reset_day=row.reset_day,
            key_problem=row.key_problem,
            key_problem_at=row.key_problem_at,
            tiles=int(counts.get(src.id) or 0),
            provider_usage=usage,
        )

    return [state(src) for src in SOURCES]


def _decrypt(box: SecretBox, token: str | None) -> str | None:
    if not token:
        return None
    try:
        return box.decrypt(token)
    except ValueError:  # the secret key of the installation changed: as if never entered
        return None


# Fields of `update`; a field left out keeps its value.
UNSET: Any = object()


async def update(
    db: AsyncSession,
    box: SecretBox,
    account_id: UUID,
    source_id: str,
    *,
    transport: httpx2.AsyncBaseTransport | None = None,
    site: str | None = None,
    enabled: bool = UNSET,
    api_key: str | None = UNSET,
    usage_token: str | None = UNSET,
    reset_day: int | None = UNSET,
) -> str | None:
    """Changes the settings of a source; an empty or null key or token deletes it. A new key is
    checked with the provider, as if asked from `site` (the address of the app in the browser,
    for keys restricted to it); returns "unreachable" when that could not be done."""
    src = source(source_id)
    rows = await _rows(db, account_id)
    row = _row(rows, account_id, source_id)
    db.add(row)
    check = None
    if api_key is not UNSET:
        api_key = (api_key or "").strip() or None
        row.api_key_encrypted = box.encrypt(api_key) if api_key else None
        row.key_problem = row.key_problem_at = None
        if api_key is None:
            row.enabled = False
        elif src.key_check_url:
            check = await _check_and_store(row, src, api_key, site, transport)
    if usage_token is not UNSET:
        if not src.usage_token:
            raise ApiError(422, "map_source_no_usage_token")
        usage_token = (usage_token or "").strip() or None
        row.usage_token_encrypted = box.encrypt(usage_token) if usage_token else None
        row.provider_usage = None
        if usage_token:
            row.provider_usage = await _provider_usage(src, usage_token, None, transport)
    if reset_day is not UNSET:
        if reset_day is not None and not 1 <= reset_day <= 31:
            raise ApiError(422, "map_source_reset_day_invalid")
        row.reset_day = reset_day
    if enabled is not UNSET:
        if enabled and src.needs_key and not row.api_key_encrypted:
            raise ApiError(422, "map_source_needs_key")
        row.enabled = enabled
    await db.commit()
    return check


async def check_key(
    db: AsyncSession,
    box: SecretBox,
    account_id: UUID,
    source_id: str,
    transport: httpx2.AsyncBaseTransport | None = None,
    site: str | None = None,
) -> str | None:
    """Asks the provider about the stored key again (after a problem); "unreachable" or None."""
    src = source(source_id)
    row = (await _rows(db, account_id)).get(source_id)
    key = _decrypt(box, row.api_key_encrypted) if row else None
    if row is None or key is None:
        raise ApiError(422, "map_source_needs_key")
    if not src.key_check_url:
        row.key_problem = row.key_problem_at = None
        await db.commit()
        return None
    check = await _check_and_store(row, src, key, site, transport)
    await db.commit()
    return check


async def _check_and_store(
    row: MapSourceSetting,
    src: Source,
    key: str,
    site: str | None,
    transport: httpx2.AsyncBaseTransport | None,
) -> str | None:
    try:
        problem = await _ask_about_key(src, key, site, transport)
    except httpx2.HTTPError:
        return "unreachable"
    row.key_problem = problem
    row.key_problem_at = utcnow() if problem else None
    return None


def _client(transport: httpx2.AsyncBaseTransport | None) -> httpx2.AsyncClient:
    headers = {"User-Agent": f"immich-steward/{__version__}"}
    return httpx2.AsyncClient(timeout=PROVIDER_TIMEOUT_S, headers=headers, transport=transport)


async def _ask_about_key(
    src: Source, key: str, site: str | None, transport: httpx2.AsyncBaseTransport | None
) -> str | None:
    """None when the provider accepts the key, else the problem. Raises on network errors and
    on answers that tell nothing (a server error). A key restricted to the address of the app
    (Esri referrers, MapTiler allowed origins) is checked with that address, as the browser sends
    it with the tiles; without it the provider would refuse the key."""
    assert src.key_check_url
    headers = {"Origin": site, "Referer": site + "/"} if site else {}
    async with _client(transport) as http:
        response = await http.get(fill(src.key_check_url, key), headers=headers)
    if response.status_code in (401, 403):
        return INVALID
    if response.status_code == 429:
        return EXHAUSTED
    if response.status_code != 200:
        raise httpx2.HTTPStatusError("no answer", request=response.request, response=response)
    # ArcGIS reports errors in the body, often with HTTP 200.
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return EXHAUSTED if error.get("code") == 429 else INVALID
    return None


async def report(
    db: AsyncSession,
    account_id: UUID,
    tiles: dict[str, int],
    problems: dict[str, str],
) -> None:
    """Adds the tiles the browser loaded since its last report and the key problems it saw."""
    if any(i not in BY_ID for i in [*tiles, *problems]):
        raise ApiError(422, "map_source_not_found")
    if any(not 0 <= n <= MAX_REPORTED_TILES for n in tiles.values()):
        raise ApiError(422, "map_tiles_invalid")
    if any(p not in KEY_PROBLEMS for p in problems.values()):
        raise ApiError(422, "map_key_problem_invalid")
    rows = await _rows(db, account_id)
    await _roll_periods(db, rows)
    today = utcnow().date()
    for source_id, count in tiles.items():
        if not count:
            continue
        statement = insert(MapTileUsage).values(
            account_id=account_id, source_id=source_id, day=today, tiles=count
        )
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=["account_id", "source_id", "day"],
                set_={"tiles": MapTileUsage.tiles + statement.excluded.tiles},
            )
        )
    for source_id, problem in problems.items():
        row = _row(rows, account_id, source_id)
        if row.key_problem != problem:
            row.key_problem, row.key_problem_at = problem, utcnow()
    db.add_all(rows.values())
    await db.commit()


async def reset_count(db: AsyncSession, account_id: UUID, source_id: str) -> None:
    source(source_id)
    rows = await _rows(db, account_id)
    row = _row(rows, account_id, source_id)
    db.add(row)
    await _reset_count(db, row, utcnow())
    await db.commit()


async def refresh_provider_usage(
    db: AsyncSession,
    box: SecretBox,
    account_id: UUID,
    *,
    force: bool = False,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> None:
    """Asks the providers about the usage where the account gave a token and the last answer is
    old (or always, with `force`)."""
    rows = await _rows(db, account_id)
    changed = False
    for row in rows.values():
        src = BY_ID[row.source_id]
        token = _decrypt(box, row.usage_token_encrypted)
        if not src.usage_token or token is None:
            continue
        last = row.provider_usage
        if last and not force:
            fetched = datetime.fromisoformat(last["fetched_at"])
            if utcnow() - fetched < PROVIDER_USAGE_TTL:
                continue
        row.provider_usage = await _provider_usage(src, token, last, transport)
        changed = True
    if changed:
        await db.commit()


MAPTILER_TIMELINE = "https://service.maptiler.com/v1/analytics/api_usage/timeline"


async def _provider_usage(
    src: Source,
    token: str,
    last: dict[str, Any] | None,
    transport: httpx2.AsyncBaseTransport | None,
) -> dict[str, Any]:
    """The MapTiler Analytics API: requests of the current billing period, per day (today is
    not there yet), and MapTiler's estimate for the whole period."""
    assert src.id == "maptiler"
    params = {"period": "current_billing_period", "classifier": "services", "group": "request"}
    headers = {"Authorization": f"Token {token}"}
    fetched_at = utcnow().isoformat()
    try:
        async with _client(transport) as http:
            response = await http.get(MAPTILER_TIMELINE, params=params, headers=headers)
        if response.status_code in (401, 403):
            return (last or _empty_usage()) | {"error": "token_invalid", "fetched_at": fetched_at}
        response.raise_for_status()
        body = response.json()
    except (httpx2.HTTPError, ValueError):
        return (last or _empty_usage()) | {"error": "unreachable", "fetched_at": fetched_at}
    requests = [d for d in body.get("datasets", []) if d.get("group_id") == "request"]
    used = sum(point["value"] for d in requests for point in d.get("data", []))
    estimates = [d["estimated_data"]["value"] for d in requests if d.get("estimated_data")]
    usage = ProviderUsage(
        used=used,
        estimated=sum(estimates) if estimates else None,
        since=body.get("since"),
        until=body.get("until"),
        fetched_at=fetched_at,
    )
    return vars(usage)


def _empty_usage() -> dict[str, Any]:
    return {"used": None, "estimated": None, "since": None, "until": None}


@dataclass(frozen=True)
class Auto:
    """Sources of the automatic switching by zoom; None: the plain map."""

    far: str | None
    near: str | None
    switch_zoom: int


def default_auto(states_: list[State]) -> Auto:
    usable = [s.source.id for s in states_ if s.enabled and s.status != "no_key"]
    far = "eox" if "eox" in usable else None
    near = next((i for i in NEAR_ORDER if i in usable and i != far), far)
    return Auto(far, near, DEFAULT_SWITCH_ZOOM)


async def get_auto(db: AsyncSession, account_id: UUID, states_: list[State]) -> Auto:
    row = await db.get(MapAuto, account_id)
    if row is None:
        return default_auto(states_)
    return Auto(row.far_source, row.near_source, row.switch_zoom)


async def save_auto(db: AsyncSession, box: SecretBox, account_id: UUID, auto: Auto) -> Auto:
    """Only sources the account switched on (with their key) can be chosen (D-142)."""
    on = {s.source.id for s in await states(db, box, account_id) if s.enabled}
    if any(i is not None and i not in on for i in (auto.far, auto.near)):
        raise ApiError(422, "map_source_not_enabled")
    if not 1 <= auto.switch_zoom <= 22:
        raise ApiError(422, "map_switch_zoom_invalid")
    row = await db.get(MapAuto, account_id) or MapAuto(account_id=account_id)
    row.far_source, row.near_source, row.switch_zoom = auto.far, auto.near, auto.switch_zoom
    db.add(row)
    await db.commit()
    return auto
