# SPDX-License-Identifier: AGPL-3.0-or-later
"""The heat map of located photos over the map (D-155)."""

import json

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient

HOME = {"latitude": 42.44101, "longitude": 19.26214}
NEAR_HOME = {"latitude": 42.44139, "longitude": 19.26181}  # the same cell of about 100 m
SEA = {"latitude": 42.2864, "longitude": 18.8400}


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    add = fake_immich.add_asset
    add(taken="2024-05-01T10:00:00", exif=HOME)
    add(taken="2024-05-01T11:00:00", exif=NEAR_HOME)
    add(taken="2024-05-02T10:00:00", exif=SEA)
    add(taken="2024-05-03T10:00:00", exif=SEA, visibility="archive")
    add(taken="2024-05-04T10:00:00", exif=SEA, isTrashed=True)
    add(taken="2024-05-05T10:00:00")  # no location
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    return {item["file_name"]: item["id"] for item in items}


def cells(response_json: list[float]) -> dict[tuple[float, float], int]:
    triples = zip(response_json[0::3], response_json[1::3], response_json[2::3], strict=True)
    return {(lat, lon): int(count) for lat, lon, count in triples}


@pytest.mark.usefixtures("library")
def test_cells_of_located_photos(signed_in: TestClient) -> None:
    response = signed_in.get("/api/assets/heatmap")

    assert response.status_code == 200
    # Archived photos count, trashed ones and photos without a location do not.
    assert cells(response.json()) == {(42.441, 19.262): 2, (42.286, 18.84): 2}


@pytest.mark.usefixtures("library")
def test_compressed_when_the_browser_accepts_it(signed_in: TestClient) -> None:
    response = signed_in.get("/api/assets/heatmap", headers={"Accept-Encoding": "gzip"})
    assert response.headers["Content-Encoding"] == "gzip"
    # The test client unpacks it like a browser does.
    assert cells(response.json()) == {(42.441, 19.262): 2, (42.286, 18.84): 2}
    raw = signed_in.get("/api/assets/heatmap", headers={"Accept-Encoding": "identity"})
    assert "Content-Encoding" not in raw.headers
    assert json.loads(raw.content) == response.json()


def test_unchanged_is_not_sent_again(signed_in: TestClient, library: dict[str, str]) -> None:
    first = signed_in.get("/api/assets/heatmap")
    etag = first.headers["ETag"]

    again = signed_in.get("/api/assets/heatmap", headers={"If-None-Match": etag})
    assert again.status_code == 304

    # A location written in the app changes the map, and the ETag.
    without = library["IMG_0005.JPG"]
    point = {"latitude": 43.0, "longitude": 20.0}
    assert signed_in.put(f"/api/assets/{without}/location", json=point).status_code == 200
    changed = signed_in.get("/api/assets/heatmap", headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["ETag"] != etag
    assert cells(changed.json())[(43.0, 20.0)] == 1


def test_empty_library(signed_in: TestClient) -> None:
    response = signed_in.get("/api/assets/heatmap")
    assert response.status_code == 200
    assert response.json() == []


def test_signed_out_gets_nothing(client: TestClient) -> None:
    assert client.get("/api/assets/heatmap").status_code == 401
