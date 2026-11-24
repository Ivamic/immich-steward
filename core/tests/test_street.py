# SPDX-License-Identifier: AGPL-3.0-or-later
"""Street-level images near a point (D-244): sources, search, previews through the core."""

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import httpx2
import pytest
from conftest import WORKER_TOKEN
from fastapi.testclient import TestClient
from test_regions import photo

from steward import street, worker_queue
from steward.api.worker import PROTOCOL_VERSION

__all__ = ["photo"]

TOKEN = "MLY|123|good"
# A point in a city; the images around it, about 10, 40 and 250 m away.
LAT, LON = 48.8535, 2.348
NEAR = (48.85359, 2.348)
MIDDLE = (48.8535, 2.34855)
FAR = (48.85575, 2.348)
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def panoramax_feature(
    image_id: str, point: tuple[float, float], pano: bool = False
) -> dict[str, Any]:
    lat, lon = point
    host = f"https://storage.example.org/{image_id}"
    return {
        "id": image_id,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "datetime": "2024-05-01T10:00:00+00:00",
            "view:azimuth": 90,
            "license": "CC-BY-SA-4.0",
            "geovisio:producer": "someone",
            "pers:interior_orientation": {"field_of_view": 360 if pano else 70},
        },
        "assets": {"thumb": {"href": f"{host}/thumb.jpg"}, "sd": {"href": f"{host}/sd.jpg"}},
        "links": [{"rel": "license", "href": "https://creativecommons.org/licenses/by-sa/4.0/"}],
        "providers": [{"name": "someone", "roles": ["producer"]}],
    }


def mapillary_item(image_id: str, point: tuple[float, float]) -> dict[str, Any]:
    lat, lon = point
    return {
        "id": image_id,
        "computed_geometry": {"type": "Point", "coordinates": [lon, lat]},
        "computed_compass_angle": 370.0,
        "captured_at": 1714557600000,
        "creator": {"username": "mapper", "id": "1"},
        "is_pano": False,
        "thumb_512_url": f"https://scontent.example.org/{image_id}-512.jpg",
        "thumb_2048_url": f"https://scontent.example.org/{image_id}-2048.jpg",
    }


@dataclass
class FakeStreet:
    """Panoramax and Mapillary as the core asks them."""

    panoramax: list[dict[str, Any]] = field(default_factory=list)
    mapillary: list[dict[str, Any]] = field(default_factory=list)
    down: bool = False
    # The federated catalog of Panoramax fails; its servers answer (with these).
    catalog_down: bool = False
    # The storage gives its images without saying they are (as one of Panoramax does).
    untyped: bool = False
    servers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    asked: list[httpx2.Request] = field(default_factory=list)

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.asked.append(request)
        url = str(request.url)
        if self.down:
            return httpx2.Response(503)
        if url.startswith(street.PANORAMAX_SEARCH):
            if self.catalog_down:
                return httpx2.Response(502, text="Bad Gateway")
            return self.features(self.panoramax, request)
        for server, features in self.servers.items():
            if url.startswith(f"{server}/api/search"):
                return self.features(features, request)
        if url.startswith(street.MAPILLARY_GRAPH):
            if request.headers.get("Authorization") != f"OAuth {TOKEN}":
                return httpx2.Response(401, json={"error": {"message": "Invalid OAuth"}})
            if request.url.path == "/images":
                # Points only: the previews are asked for the nearest ones by their ids.
                points = [
                    {k: v for k, v in i.items() if not k.startswith("thumb_")}
                    for i in self.mapillary
                ]
                return httpx2.Response(200, json={"data": points})
            if ids := request.url.params.get("ids"):
                wanted = ids.split(",")
                return httpx2.Response(
                    200,
                    json={
                        i["id"]: {k: v for k, v in i.items() if k.startswith("thumb_")}
                        for i in self.mapillary
                        if i["id"] in wanted
                    },
                )
            image_id = request.url.path.strip("/")
            item = next((i for i in self.mapillary if i["id"] == image_id), None)
            return httpx2.Response(200, json=item) if item else httpx2.Response(404)
        if url.startswith(("https://storage.example.org/", "https://scontent.example.org/")):
            kind = "binary/octet-stream" if self.untyped else "image/jpeg"
            return httpx2.Response(200, content=JPEG, headers={"content-type": kind})
        return httpx2.Response(404)

    @staticmethod
    def features(features: list[dict[str, Any]], request: httpx2.Request) -> httpx2.Response:
        ids = request.url.params.get("ids")
        found = [f for f in features if ids is None or f["id"] == ids]
        return httpx2.Response(200, json={"type": "FeatureCollection", "features": found})

    def outside(self) -> list[str]:
        """Hosts asked, without the images: what left the server besides previews."""
        return [r.url.host for r in self.asked if not r.url.path.endswith(".jpg")]


@pytest.fixture
def fake(signed_in: TestClient) -> FakeStreet:
    found = FakeStreet(
        panoramax=[
            panoramax_feature("far", FAR),
            panoramax_feature("near", NEAR, pano=True),
        ],
        mapillary=[mapillary_item("111", MIDDLE)],
    )
    signed_in.app.state.map_transport = httpx2.MockTransport(found.handler)  # type: ignore[attr-defined]
    signed_in.app.state.street_links = street.Links()  # type: ignore[attr-defined]
    return found


def turn_on(client: TestClient, source_id: str, **body: Any) -> dict[str, Any]:
    response = client.put(f"/api/street/sources/{source_id}", json={"enabled": True, **body})
    assert response.status_code == 200
    found: dict[str, Any] = response.json()
    return found


def near(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/street/near", params={"lat": LAT, "lon": LON, **params})
    assert response.status_code == 200
    found: dict[str, Any] = response.json()
    return found


def test_nothing_leaves_until_a_source_is_on(signed_in: TestClient, fake: FakeStreet) -> None:
    sources = {s["id"]: s for s in signed_in.get("/api/street/sources").json()}
    assert not sources["panoramax"]["enabled"] and not sources["mapillary"]["enabled"]
    assert sources["mapillary"]["needs_key"] and not sources["panoramax"]["needs_key"]
    assert near(signed_in) == {"images": [], "sources": []}
    assert fake.asked == []
    # The card shows them only when the user turned them on.
    assert signed_in.get("/api/settings").json()["street_shown"] is False


def test_images_near_the_point_nearest_first(signed_in: TestClient, fake: FakeStreet) -> None:
    turn_on(signed_in, "panoramax")
    mapillary = turn_on(signed_in, "mapillary", api_key=TOKEN)
    assert mapillary["has_key"] and mapillary["key_problem"] is None
    found = near(signed_in)
    # The one 250 m away is outside the 100 m.
    assert [(i["source"], i["id"]) for i in found["images"]] == [
        ("panoramax", "near"),
        ("mapillary", "111"),
    ]
    first, second = found["images"]
    assert first["pano"] and first["heading"] == 90 and first["author"] == "someone"
    assert 5 < first["distance_m"] < 15
    assert second["heading"] == 10 and second["taken_at"] == "2024-05-01T10:00:00Z"
    assert second["license"] == "CC-BY-SA-4.0" and "pKey=111" in second["page_url"]
    assert {s["id"]: (s["status"], s["count"]) for s in found["sources"]} == {
        "panoramax": ("ok", 1),
        "mapillary": ("ok", 1),
    }
    assert [i["id"] for i in near(signed_in, radius=300)["images"]] == ["near", "111", "far"]
    # Only the providers' APIs: the point, never a photo.
    assert set(fake.outside()) == {"api.panoramax.xyz", "graph.mapillary.com"}


def test_previews_come_through_the_core(signed_in: TestClient, fake: FakeStreet) -> None:
    turn_on(signed_in, "panoramax")
    near(signed_in)
    preview = signed_in.get("/api/street/image/panoramax/near", params={"size": "large"})
    assert (preview.status_code, preview.content) == (200, JPEG)
    assert preview.headers["content-type"] == "image/jpeg"
    assert fake.asked[-1].url.path == "/near/sd.jpg"

    # After a restart of the core: the provider is asked for the image by its id.
    signed_in.app.state.street_links = street.Links()  # type: ignore[attr-defined]
    assert signed_in.get("/api/street/image/panoramax/near").status_code == 200
    # Never an address from the browser, nor an image of a source that is off.
    assert signed_in.get("/api/street/image/panoramax/unknown").status_code == 404
    assert signed_in.get("/api/street/image/mapillary/111").status_code == 404
    assert signed_in.get("/api/street/image/panoramax/..%2Fx").status_code in (404, 422)


def test_a_refused_token(signed_in: TestClient, fake: FakeStreet) -> None:
    bad = turn_on(signed_in, "mapillary", api_key="MLY|1|bad")
    assert bad["key_problem"] == "invalid"
    assert near(signed_in)["sources"] == [{"id": "mapillary", "status": "invalid_key", "count": 0}]
    no_key = turn_on(signed_in, "mapillary", api_key="")
    assert not no_key["has_key"] and no_key["key_problem"] is None
    assert near(signed_in)["sources"] == [{"id": "mapillary", "status": "no_key", "count": 0}]
    assert turn_on(signed_in, "mapillary", api_key=TOKEN)["key_problem"] is None


def test_a_source_down_leaves_the_others(signed_in: TestClient, fake: FakeStreet) -> None:
    turn_on(signed_in, "panoramax")
    fake.down = True
    assert near(signed_in) == {
        "images": [],
        "sources": [{"id": "panoramax", "status": "unavailable", "count": 0}],
    }
    response = signed_in.get("/api/street/near", params={"lat": 91, "lon": 0})
    assert response.status_code == 422


def test_the_square_stays_within_mapillary_limit() -> None:
    west, south, east, north = street.bbox(60.0, 10.0, street.MOST_RADIUS_M)
    assert (east - west) * (north - south) < 0.01


def test_the_nearest_of_a_busy_street(signed_in: TestClient, fake: FakeStreet) -> None:
    """Mapillary gives the points of a whole square: the nearest are picked, not the first, and
    a drive with a frame every metre is thinned to one image per few metres."""
    fake.mapillary = [
        mapillary_item(str(1000 + n), (LAT + 0.00085 - n * 0.00001, LON)) for n in range(120)
    ]
    turn_on(signed_in, "mapillary", api_key=TOKEN)
    found = near(signed_in)["images"]
    assert found[0]["distance_m"] < 2
    assert all(a["distance_m"] <= b["distance_m"] for a, b in pairwise(found))
    # About 200 m of street, one image per 8 m: some 25, not a hundred frames.
    assert 15 <= len(found) <= 30


def test_a_series_does_not_fill_the_strip(signed_in: TestClient, fake: FakeStreet) -> None:
    """A dashcam drive: frames a few metres apart looking the same way, of one series; a single
    image of another series further away still makes it in."""
    drive = [
        mapillary_item(str(2000 + n), (LAT + n * 0.0001, LON)) | {"sequence": "drive"}
        for n in range(8)
    ]
    other = mapillary_item("3000", (LAT, LON + 0.0009)) | {"sequence": "walk"}
    fake.mapillary = [*drive, other]
    turn_on(signed_in, "mapillary", api_key=TOKEN)
    found = [i["id"] for i in near(signed_in)["images"]]
    assert len([i for i in found if i.startswith("2")]) == street.SERIES_MOST
    assert "3000" in found


def test_panoramax_servers_when_the_catalog_is_down(
    signed_in: TestClient, fake: FakeStreet
) -> None:
    fake.catalog_down = True
    first, second = street.PANORAMAX_SERVERS
    fake.servers = {
        first: [panoramax_feature("osm", NEAR)],
        second: [panoramax_feature("ign", MIDDLE)],
    }
    turn_on(signed_in, "panoramax")
    found = near(signed_in)
    assert [i["id"] for i in found["images"]] == ["osm", "ign"]
    assert found["sources"] == [{"id": "panoramax", "status": "ok", "count": 2}]
    # A preview asked after a restart is found there too.
    signed_in.app.state.street_links = street.Links()  # type: ignore[attr-defined]
    assert signed_in.get("/api/street/image/panoramax/ign").status_code == 200
    fake.servers = {}
    assert near(signed_in)["sources"][0]["status"] == "unavailable"


def test_one_source_at_a_time(signed_in: TestClient, fake: FakeStreet) -> None:
    turn_on(signed_in, "panoramax")
    turn_on(signed_in, "mapillary", api_key=TOKEN)
    only = near(signed_in, source="mapillary")
    assert [s["id"] for s in only["sources"]] == ["mapillary"]
    assert {i["source"] for i in only["images"]} == {"mapillary"}
    response = signed_in.get("/api/street/near", params={"lat": LAT, "lon": LON, "source": "x"})
    assert response.status_code == 404


AUTH = {"Authorization": f"Bearer {WORKER_TOKEN}"}


def street_worker(client: TestClient) -> dict[str, str]:
    body = {
        "name": "laptop",
        "modules": ["street"],
        "device": "cuda",
        "version": "0.14.0",
        "protocol_version": PROTOCOL_VERSION,
    }
    worker_id = client.post("/api/worker/register", json=body, headers=AUTH).json()["worker_id"]
    return AUTH | {"X-Worker-Id": worker_id}


def test_an_image_served_untyped_is_still_an_image(signed_in: TestClient, fake: FakeStreet) -> None:
    """A storage of Panoramax gives its JPEGs as "binary/octet-stream": told by their bytes. Not
    an image stays refused."""
    turn_on(signed_in, "panoramax")
    near(signed_in)
    fake.untyped = True
    preview = signed_in.get("/api/street/image/panoramax/near")
    assert (preview.status_code, preview.headers["content-type"]) == (200, "image/jpeg")
    assert street._image_kind(b"<html>", "text/html") is None
    png = b"\x89PNG\r\n\x1a\nrest"
    assert street._image_kind(png, "binary/octet-stream") == "image/png"
    webp = b"RIFF\x00\x00\x00\x00WEBPVP8 "
    assert street._image_kind(webp, "") == "image/webp"


def test_compare_the_photo_with_the_images(
    signed_in: TestClient, fake: FakeStreet, photo: tuple[str, str]
) -> None:
    asset, _ = photo
    url = f"/api/street/compare/{asset}"
    assert signed_in.get(url).json() == {
        "status": "none",
        "error_code": None,
        "workers": 0,
        "results": [],
    }
    turn_on(signed_in, "panoramax")
    keys = [f"{i['source']}:{i['id']}" for i in near(signed_in)["images"]]
    assert keys == ["panoramax:near"]
    # Only images of a source switched on.
    off = signed_in.post(url, json={"images": ["mapillary:111"]})
    assert (off.status_code, off.json()["code"]) == (409, "street_source_off")
    assert signed_in.post(url, json={"images": ["../x"]}).status_code == 422

    worker = street_worker(signed_in)
    asked = signed_in.post(url, json={"images": keys}).json()
    assert (asked["status"], asked["workers"]) == ("queued", 1)
    job = signed_in.post("/api/worker/lease", json={"modules": ["street"]}, headers=worker).json()
    assert job["others"] == keys
    image = f"/api/worker/jobs/{job['job_id']}/image"
    got = signed_in.get(image, params={"other": "panoramax:near"}, headers=worker)
    assert (got.status_code, got.content) == (200, JPEG)
    # Only an image the job names.
    unnamed = signed_in.get(image, params={"other": "panoramax:far"}, headers=worker)
    assert unnamed.status_code == 404
    result = {
        "module_version": "1",
        "candidates": [],
        "pairs": [
            {
                "other": "panoramax:near",
                "matches": 300,
                "inliers": 140,
                "lines": [[0.1, 0.2, 0.3, 0.4]],
                "similarity": 0.42,
                "checked": True,
                "view": 2,
                "offset": -20.5,
                "spread": 3.0,
                "fov": 52.0,
            },
            {"other": "panoramax:far", "matches": 1, "inliers": 1},
        ],
    }
    done = signed_in.post(f"/api/worker/jobs/{job['job_id']}/result", json=result, headers=worker)
    assert done.status_code == 204
    found = signed_in.get(url).json()
    assert found["status"] == "done"
    assert found["results"] == [
        {
            "key": "panoramax:near",
            "similarity": 0.42,
            "checked": True,
            "matches": 300,
            "inliers": 140,
            "lines": [[0.1, 0.2, 0.3, 0.4]],
            "view": 2,
            "offset": -20.5,
            "spread": 3.0,
            "fov": 52.0,
        }
    ]
    # Not as an ordinary module: it needs the images of the strip.
    assert signed_in.post(f"/api/assets/{asset}/modules/street/run").status_code == 404


def test_a_whole_strip_is_compared(
    signed_in: TestClient, fake: FakeStreet, photo: tuple[str, str]
) -> None:
    """As many images as the strip shows: the answer about each of them is taken (once the
    answer of more than 30 was refused, and the comparison failed after three tries)."""
    asset, _ = photo
    fake.panoramax = [
        panoramax_feature(f"img{n:02d}", (LAT + n * 0.00001, LON + (n % 7) * 0.00012))
        for n in range(street.NEAR_MOST)
    ]
    turn_on(signed_in, "panoramax")
    keys = [f"{i['source']}:{i['id']}" for i in near(signed_in, radius=300)["images"]]
    assert len(keys) > worker_queue.MAX_OTHERS
    worker = street_worker(signed_in)
    signed_in.post(f"/api/street/compare/{asset}", json={"images": keys})
    job = signed_in.post("/api/worker/lease", json={"modules": ["street"]}, headers=worker).json()
    assert len(job["others"]) == len(keys)
    pairs = [{"other": key, "matches": 0, "inliers": 0, "similarity": 0.1} for key in keys]
    body = {"module_version": "1", "candidates": [], "pairs": pairs}
    done = signed_in.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)
    assert done.status_code == 204
    assert len(signed_in.get(f"/api/street/compare/{asset}").json()["results"]) == len(keys)


def test_comparisons_add_up(
    signed_in: TestClient, fake: FakeStreet, photo: tuple[str, str]
) -> None:
    """Searched around a matched image, only the new images are compared: the answers about the
    earlier ones stay (D-246); those of another version of the module do not."""
    asset, _ = photo
    fake.panoramax = [
        panoramax_feature(name, (LAT + n * 0.0001, LON)) for n, name in enumerate("abc")
    ]
    turn_on(signed_in, "panoramax")
    worker = street_worker(signed_in)

    def compare(keys: list[str], version: str, inliers: int) -> list[dict[str, object]]:
        signed_in.post(f"/api/street/compare/{asset}", json={"images": keys})
        job = signed_in.post(
            "/api/worker/lease", json={"modules": ["street"]}, headers=worker
        ).json()
        pairs = [{"other": key, "matches": inliers, "inliers": inliers} for key in keys]
        body = {"module_version": version, "candidates": [], "pairs": pairs}
        done = signed_in.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)
        assert done.status_code == 204
        results = signed_in.get(f"/api/street/compare/{asset}").json()["results"]
        return sorted(results, key=lambda r: str(r["key"]))

    first = compare(["panoramax:a", "panoramax:b"], "2", 10)
    assert [r["key"] for r in first] == ["panoramax:a", "panoramax:b"]
    second = compare(["panoramax:b", "panoramax:c"], "2", 20)
    assert [(r["key"], r["inliers"]) for r in second] == [
        ("panoramax:a", 10),
        ("panoramax:b", 20),
        ("panoramax:c", 20),
    ]
    newer = compare(["panoramax:c"], "3", 30)
    assert [(r["key"], r["inliers"]) for r in newer] == [("panoramax:c", 30)]
