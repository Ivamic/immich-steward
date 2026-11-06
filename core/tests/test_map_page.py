# SPDX-License-Identifier: AGPL-3.0-or-later
"""The page "Map" (D-207): photos with a location gathered by the zoom, and those of a place."""

from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient

from steward.gallery import map_cell_degrees

WORLD = {"south": -90, "west": -180, "north": 90, "east": 180}
KOTOR = (42.4247, 18.7712)


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    """Three photos in Kotor ~100 m apart, one in Rome, one on Fiji (east of the 180th meridian
    is west), one without a location, one video in Kotor."""
    photos: dict[str, dict[str, Any]] = {
        "kotor1.jpg": {"latitude": KOTOR[0], "longitude": KOTOR[1]},
        "kotor2.jpg": {"latitude": KOTOR[0] + 0.001, "longitude": KOTOR[1]},
        "kotor3.jpg": {"latitude": KOTOR[0], "longitude": KOTOR[1] + 0.001},
        "rome.jpg": {"latitude": 41.9, "longitude": 12.5},
        "fiji.jpg": {"latitude": -17.8, "longitude": 179.9},
        "nowhere.jpg": {},
    }
    for hour, (name, exif) in enumerate(photos.items()):
        fake_immich.add_asset(
            taken=f"2024-05-01T{10 + hour}:00:00", originalFileName=name, exif=exif
        )
    fake_immich.add_asset(
        taken="2024-05-01T20:00:00",
        originalFileName="kotor.mp4",
        type="VIDEO",
        exif={"latitude": KOTOR[0], "longitude": KOTOR[1]},
    )
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05", "show": ["todo", "with"]})
    return {item["file_name"]: item["id"] for item in items.json()}


def cells(client: TestClient, zoom: float, **params: Any) -> list[dict[str, Any]]:
    answer = client.get("/api/assets/map/cells", params=WORLD | {"zoom": zoom} | params)
    assert answer.status_code == 200
    found: list[dict[str, Any]] = answer.json()["cells"]
    return sorted(found, key=lambda c: -c["photos"])


def test_photos_gather_by_the_zoom(signed_in: TestClient, library: dict[str, str]) -> None:
    # Far: Kotor (3 photos and the video) is one circle, Rome and Fiji alone; no photo without
    # a location.
    far = cells(signed_in, 3)
    assert [c["photos"] for c in far] == [4, 1, 1]
    assert far[0]["asset_id"] is None
    assert {c["asset_id"] for c in far[1:]} == {library["rome.jpg"], library["fiji.jpg"]}
    # Close: the photos of Kotor ~100 m apart are apart.
    assert sorted(c["photos"] for c in cells(signed_in, 18)) == [1, 1, 1, 1, 2]
    # The cell of a far zoom holds its photos.
    kotor = far[0]
    bounds = kotor["bounds"]
    assert bounds["south"] <= KOTOR[0] <= bounds["north"]
    assert bounds["north"] - bounds["south"] == pytest.approx(map_cell_degrees(3))


def test_the_filters_of_the_gallery_apply(signed_in: TestClient, library: dict[str, str]) -> None:
    assert [c["photos"] for c in cells(signed_in, 3, type="image")] == [3, 1, 1]
    assert [c["photos"] for c in cells(signed_in, 3, type="video")] == [1]
    assert cells(signed_in, 3, date_from="2024-06-01") == []


def test_only_the_bounds_asked_for(signed_in: TestClient, library: dict[str, str]) -> None:
    europe = {"south": 35, "west": 5, "north": 50, "east": 25}
    assert sum(c["photos"] for c in cells(signed_in, 5, **europe)) == 5
    # Across the 180th meridian: west is east of east.
    pacific = {"south": -30, "west": 170, "north": 0, "east": -170}
    assert [c["asset_id"] for c in cells(signed_in, 5, **pacific)] == [library["fiji.jpg"]]


def test_the_photos_of_a_place_newest_first(signed_in: TestClient, library: dict[str, str]) -> None:
    kotor = cells(signed_in, 3)[0]["bounds"]
    answer = signed_in.get("/api/assets/map/photos", params=kotor | {"limit": 2}).json()
    assert answer["total"] == 4
    assert [p["file_name"] for p in answer["photos"]] == ["kotor.mp4", "kotor3.jpg"]
    rest = signed_in.get("/api/assets/map/photos", params=kotor | {"offset": 2}).json()
    assert [p["file_name"] for p in rest["photos"]] == ["kotor2.jpg", "kotor1.jpg"]
