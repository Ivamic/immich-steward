# SPDX-License-Identifier: AGPL-3.0-or-later
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import httpx2
import pytest
from conftest import FakeImmich
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from steward.map_sources import period_start
from steward.models import MapSourceSetting

ESRI_KEY = "esri-good-key-1234"
MAPTILER_KEY = "maptiler-good-key-5678"
SERVICE_TOKEN = "service-token-9999"


@dataclass
class FakeProviders:
    """Esri and MapTiler, as far as the key checks and the usage are concerned."""

    esri_keys: set[str] = field(default_factory=lambda: {ESRI_KEY})
    maptiler_keys: set[str] = field(default_factory=lambda: {MAPTILER_KEY})
    down: bool = False
    # Keys restricted to an address of the app: accepted only with it as the referrer.
    referrers: dict[str, str] = field(default_factory=dict)
    requests: list[httpx2.Request] = field(default_factory=list)

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.down:
            raise httpx2.ConnectError("no network", request=request)
        url = request.url
        if url.host == "basemapstyles-api.arcgis.com":
            token = url.params.get("token", "")
            allowed = self.referrers.get(token)
            if allowed and not request.headers.get("referer", "").startswith(allowed):
                error = {"code": 403, "message": "Invalid referer", "details": []}
                return httpx2.Response(403, json={"error": error})
            if token in self.esri_keys:
                return httpx2.Response(200, json={"version": 8, "sources": {}})
            error = {"code": 498, "message": "Token Invalid.", "details": []}
            return httpx2.Response(401, json={"error": error})
        if url.host == "api.maptiler.com" and url.path.endswith("/tiles.json"):
            if url.params.get("key") in self.maptiler_keys:
                return httpx2.Response(200, json={"tilejson": "2.2.0"})
            return httpx2.Response(403, text="Invalid key - Get your FREE key at …")
        if url.host == "service.maptiler.com":
            if request.headers.get("authorization") != f"Token {SERVICE_TOKEN}":
                return httpx2.Response(401, json={"errors": [{"msg": "Unauthorized"}]})
            return httpx2.Response(200, json=TIMELINE)
        return httpx2.Response(404)


TIMELINE = {
    "since": "2026-10-01",
    "until": "2026-10-31",
    "datasets": [
        {
            "group_id": "request",
            "item_id": "tiles",
            "data": [{"date": "2026-10-01", "value": 300}, {"date": "2026-10-02", "value": 200}],
            "estimated_data": {"date": "2026-10-31", "value": 7000},
        },
        {
            "group_id": "session",
            "item_id": "maps",
            "data": [{"date": "2026-10-01", "value": 9}],
        },
    ],
    "legend": [],
}


@pytest.fixture
def providers(signed_in: TestClient) -> FakeProviders:
    fake = FakeProviders()
    signed_in.app.state.map_transport = httpx2.MockTransport(fake.handler)  # type: ignore[attr-defined]
    return fake


def in_db[T](client: TestClient, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async def run() -> T:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return await work(db)

    return client.portal.call(run)  # type: ignore[union-attr]


def sources(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/map-sources")
    assert response.status_code == 200
    return {s["id"]: s for s in response.json()["sources"]}


def config_sources(client: TestClient) -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in client.get("/api/config/map").json()["sources"]}


def put(client: TestClient, source_id: str, **body: Any) -> httpx2.Response:
    return client.put(f"/api/map-sources/{source_id}", json=body)


def test_sources_require_sign_in(client: TestClient) -> None:
    assert client.get("/api/map-sources").status_code == 401
    assert client.post("/api/map-sources/report", json={}).status_code == 401


def test_all_off_by_default(signed_in: TestClient, providers: FakeProviders) -> None:
    items = sources(signed_in)
    assert list(items) == ["eox", "esri", "maptiler"]
    assert not any(s["enabled"] for s in items.values())
    assert {i: s["status"] for i, s in items.items()} == {
        "eox": "ok",
        "esri": "no_key",
        "maptiler": "no_key",
    }
    assert items["eox"]["years"][0] == 2025  # the latest is the default
    assert items["maptiler"]["usage_token_supported"] is True
    assert items["esri"]["usage_url"] == "https://location.arcgis.com/usage/"
    assert items["maptiler"]["usage_url"] == "https://cloud.maptiler.com/account/analytics"
    # Nothing to load: no tile addresses while a source is off, and no requests to providers.
    for src in config_sources(signed_in).values():
        assert all(v["tiles"] is None for v in src["variants"])
    assert signed_in.get("/api/config/map").json()["auto"] == {
        "far": None,
        "near": None,
        "switch_zoom": 14,
    }
    assert providers.requests == []


def test_eox_needs_no_key(signed_in: TestClient, providers: FakeProviders) -> None:
    assert put(signed_in, "eox", enabled=True).json()["enabled"] is True
    eox = config_sources(signed_in)["eox"]
    assert eox["variants"][0]["id"] == "2025"
    assert eox["variants"][0]["tiles"] == (
        "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2025_3857/default/g/{z}/{y}/{x}.jpg"
    )
    # The 2016 layer has no year in its name.
    [y2016] = [v for v in eox["variants"] if v["id"] == "2016"]
    assert "/s2cloudless_3857/" in y2016["tiles"]
    assert "2016 &amp; 2017" in y2016["attribution"]
    assert signed_in.get("/api/config/map").json()["auto"]["far"] == "eox"


def test_a_source_with_a_key_cannot_go_on_without_one(
    signed_in: TestClient, providers: FakeProviders
) -> None:
    response = put(signed_in, "esri", enabled=True)
    assert response.status_code == 422
    assert response.json()["code"] == "map_source_needs_key"


def test_key_is_stored_encrypted_and_shown_masked(
    signed_in: TestClient, providers: FakeProviders
) -> None:
    item = put(signed_in, "esri", api_key=f"  {ESRI_KEY} ", enabled=True).json()
    assert (item["enabled"], item["status"], item["key"]) == (True, "ok", "••••1234")
    assert item["key_check"] is None
    assert ESRI_KEY not in signed_in.get("/api/map-sources").text

    stored = in_db(signed_in, lambda db: db.scalar(select(MapSourceSetting.api_key_encrypted)))
    assert stored and ESRI_KEY not in stored

    # The tiles and the copyright text are loaded by the browser, with the key.
    esri = config_sources(signed_in)["esri"]
    assert esri["variants"][0]["tiles"].endswith(f"/tile/{{z}}/{{y}}/{{x}}?token={ESRI_KEY}")
    assert esri["copyright_url"].endswith(f"?f=json&token={ESRI_KEY}")
    assert "Vantor" in esri["copyright"]
    assert "{copyright}" in esri["variants"][0]["attribution"]


def test_a_key_the_provider_refuses(signed_in: TestClient, providers: FakeProviders) -> None:
    item = put(signed_in, "maptiler", api_key="wrong", enabled=True).json()
    assert (item["enabled"], item["status"]) == (True, "invalid")
    assert item["key_problem_at"] is not None
    assert config_sources(signed_in)["maptiler"]["status"] == "invalid"

    providers.maptiler_keys.add("wrong")  # fixed on the provider side: ask again
    assert signed_in.post("/api/map-sources/maptiler/check").json()["status"] == "ok"


def test_esri_reports_errors_in_the_body(signed_in: TestClient, providers: FakeProviders) -> None:
    def ok_with_error(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"error": {"code": 498, "message": "Invalid token."}})

    signed_in.app.state.map_transport = httpx2.MockTransport(ok_with_error)  # type: ignore[attr-defined]
    assert put(signed_in, "esri", api_key=ESRI_KEY).json()["status"] == "invalid"


def test_key_restricted_to_the_app_address(signed_in: TestClient, providers: FakeProviders) -> None:
    providers.referrers[ESRI_KEY] = "http://192.168.1.10:8080"
    # The browser says where the settings were saved from; the check goes as from there.
    origin = {"origin": "http://192.168.1.10:8080"}
    response = signed_in.put("/api/map-sources/esri", json={"api_key": ESRI_KEY}, headers=origin)
    assert response.json()["status"] == "ok"
    assert providers.requests[-1].headers["referer"] == "http://192.168.1.10:8080/"

    other = {"referer": "http://steward.lan/settings"}
    response = signed_in.post("/api/map-sources/esri/check", headers=other)
    assert response.json()["status"] == "invalid"


def test_provider_unreachable(signed_in: TestClient, providers: FakeProviders) -> None:
    providers.down = True
    item = put(signed_in, "esri", api_key=ESRI_KEY, enabled=True).json()
    # Kept as it is; the problem will show on the map if there is one.
    assert (item["status"], item["key_check"]) == ("ok", "unreachable")


def test_deleting_the_key_switches_the_source_off(
    signed_in: TestClient, providers: FakeProviders
) -> None:
    put(signed_in, "esri", api_key=ESRI_KEY, enabled=True)
    item = put(signed_in, "esri", api_key="").json()
    assert (item["enabled"], item["key"], item["status"]) == (False, None, "no_key")
    assert config_sources(signed_in)["esri"]["variants"][0]["tiles"] is None


def test_keys_are_per_account(
    signed_in: TestClient, providers: FakeProviders, fake_immich: FakeImmich
) -> None:
    put(signed_in, "esri", api_key=ESRI_KEY, enabled=True)
    signed_in.post("/api/auth/logout")
    fake_immich.user_id = FakeImmich().user_id  # the same Immich key now belongs to another user
    assert signed_in.post("/api/auth/login", json={"api_key": "valid-key"}).status_code == 200
    assert sources(signed_in)["esri"]["key"] is None
    assert ESRI_KEY not in signed_in.get("/api/config/map").text


def test_own_tile_count(signed_in: TestClient, providers: FakeProviders) -> None:
    put(signed_in, "eox", enabled=True)
    for tiles in (10, 5):
        response = signed_in.post("/api/map-sources/report", json={"tiles": {"eox": tiles}})
        assert response.status_code == 204
    assert sources(signed_in)["eox"]["tiles"] == 15

    before = datetime.now(UTC)
    reset = signed_in.post("/api/map-sources/eox/reset-count").json()
    assert reset["tiles"] == 0
    assert datetime.fromisoformat(reset["counted_since"]) >= before


def test_bad_reports(signed_in: TestClient) -> None:
    for body in (
        {"tiles": {"nope": 1}},
        {"tiles": {"eox": -1}},
        {"tiles": {"eox": 10**9}},
        {"problems": {"esri": "broken"}},
    ):
        assert signed_in.post("/api/map-sources/report", json=body).status_code == 422


def test_exhausted_until_a_new_period(signed_in: TestClient, providers: FakeProviders) -> None:
    put(signed_in, "esri", api_key=ESRI_KEY, enabled=True)
    body = {"tiles": {"esri": 3}, "problems": {"esri": "exhausted"}}
    assert signed_in.post("/api/map-sources/report", json=body).status_code == 204
    assert config_sources(signed_in)["esri"]["status"] == "exhausted"
    # A reset by hand stands for the new period of the provider.
    assert signed_in.post("/api/map-sources/esri/reset-count").json()["status"] == "ok"


def test_monthly_reset_day(signed_in: TestClient, providers: FakeProviders) -> None:
    assert put(signed_in, "eox", enabled=True, reset_day=1).json()["reset_day"] == 1
    signed_in.post("/api/map-sources/report", json={"tiles": {"eox": 7}})
    assert sources(signed_in)["eox"]["tiles"] == 7

    async def last_year(db: AsyncSession) -> None:
        await db.execute(
            update(MapSourceSetting).values(counted_since=datetime(2025, 1, 1, tzinfo=UTC))
        )
        await db.commit()

    in_db(signed_in, last_year)
    eox = sources(signed_in)["eox"]
    assert eox["tiles"] == 0
    assert datetime.fromisoformat(eox["counted_since"]).day == 1

    assert put(signed_in, "eox", reset_day=0).status_code == 422
    assert put(signed_in, "eox", reset_day=None).json()["reset_day"] is None


@pytest.mark.parametrize(
    ("today", "reset_day", "start"),
    [
        (date(2026, 10, 24), 1, date(2026, 10, 1)),
        (date(2026, 10, 24), 24, date(2026, 10, 24)),
        (date(2026, 10, 24), 25, date(2026, 9, 25)),
        (date(2026, 1, 10), 15, date(2025, 12, 15)),
        # Short months start on their last day.
        (date(2026, 2, 28), 31, date(2026, 2, 28)),
        (date(2026, 3, 30), 31, date(2026, 2, 28)),
        (date(2026, 3, 31), 31, date(2026, 3, 31)),
    ],
)
def test_period_start(today: date, reset_day: int, start: date) -> None:
    assert period_start(today, reset_day) == start


def test_maptiler_usage_with_a_service_token(
    signed_in: TestClient, providers: FakeProviders
) -> None:
    item = put(signed_in, "maptiler", api_key=MAPTILER_KEY, usage_token=SERVICE_TOKEN).json()
    assert item["usage_token"] == "••••9999"
    usage = item["provider_usage"]
    assert (usage["used"], usage["estimated"], usage["error"]) == (500, 7000, None)
    assert (usage["since"], usage["until"]) == ("2026-10-01", "2026-10-31")
    # The token stays in the core.
    assert SERVICE_TOKEN not in signed_in.get("/api/config/map").text
    assert SERVICE_TOKEN not in signed_in.get("/api/map-sources").text

    # Asked again only when old, or by hand.
    asked = len(providers.requests)
    sources(signed_in)
    assert len(providers.requests) == asked
    signed_in.post("/api/map-sources/maptiler/refresh-usage")
    assert len(providers.requests) == asked + 1


def test_maptiler_wrong_token_keeps_the_last_numbers(
    signed_in: TestClient, providers: FakeProviders
) -> None:
    put(signed_in, "maptiler", usage_token=SERVICE_TOKEN)
    providers.down = True
    usage = signed_in.post("/api/map-sources/maptiler/refresh-usage").json()["provider_usage"]
    assert (usage["used"], usage["error"]) == (500, "unreachable")

    providers.down = False
    usage = put(signed_in, "maptiler", usage_token="wrong").json()["provider_usage"]
    assert (usage["used"], usage["error"]) == (None, "token_invalid")


def test_only_maptiler_takes_a_usage_token(signed_in: TestClient, providers: FakeProviders) -> None:
    response = put(signed_in, "esri", usage_token="x")
    assert response.status_code == 422
    assert response.json()["code"] == "map_source_no_usage_token"


def test_auto_switching_takes_only_sources_that_are_on(
    signed_in: TestClient, providers: FakeProviders
) -> None:
    auto = {"far": "eox", "near": "esri", "switch_zoom": 15}
    response = signed_in.put("/api/map-sources/auto", json=auto)
    assert response.status_code == 422
    assert response.json()["code"] == "map_source_not_enabled"

    put(signed_in, "eox", enabled=True)
    put(signed_in, "esri", api_key=ESRI_KEY, enabled=True)
    assert signed_in.put("/api/map-sources/auto", json=auto).json() == auto
    assert signed_in.get("/api/config/map").json()["auto"] == auto
    assert sources(signed_in) and signed_in.get("/api/map-sources").json()["auto"] == auto

    bad_zoom = auto | {"switch_zoom": 30}
    assert signed_in.put("/api/map-sources/auto", json=bad_zoom).status_code == 422


def test_default_auto_prefers_eox_far_and_a_keyed_source_near(
    signed_in: TestClient, providers: FakeProviders
) -> None:
    put(signed_in, "eox", enabled=True)
    put(signed_in, "maptiler", api_key=MAPTILER_KEY, enabled=True)
    assert signed_in.get("/api/config/map").json()["auto"] == {
        "far": "eox",
        "near": "maptiler",
        "switch_zoom": 14,
    }


def test_unknown_source(signed_in: TestClient) -> None:
    assert put(signed_in, "google", enabled=True).status_code == 404
