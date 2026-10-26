# SPDX-License-Identifier: AGPL-3.0-or-later
"""The gallery mark "a located photo was taken close in time" (D-157)."""

from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient

GPS = {"latitude": 42.4, "longitude": 19.26}
CANON = {"make": "Canon", "model": "EOS 300D"}
PHONE = {"make": "Apple", "model": "iPhone 12"}
SCANNER = {"make": "EPSON", "model": "Perfection V600"}


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    add = fake_immich.add_asset
    ids = {
        # A walk with the Canon; the phone of someone else has GPS.
        "canon_gps": add(taken="2024-05-01T10:00:00", exif=CANON | GPS),
        "canon_10min": add(taken="2024-05-01T10:10:00", exif=CANON),
        "phone_gps": add(taken="2024-05-01T14:00:00", exif=PHONE | GPS),
        "canon_after_phone": add(taken="2024-05-01T14:12:00", exif=CANON),
        "canon_20min": add(taken="2024-05-01T14:20:00", exif=CANON),
        # A scan carries the scan date: never marked, and never a neighbor.
        "scan": add(taken="2024-05-01T10:05:00", exif=SCANNER),
        "scan_gps": add(taken="2024-05-02T09:00:00", exif=SCANNER | GPS),
        "after_scan": add(taken="2024-05-02T09:05:00", exif=CANON),
        # A trashed located photo does not count.
        "trashed_gps": add(taken="2024-05-03T09:00:00", exif=CANON | GPS, isTrashed=True),
        "after_trashed": add(taken="2024-05-03T09:05:00", exif=CANON),
        # Unknown camera on both sides: not "the same camera".
        "unknown_gps": add(taken="2024-05-04T09:00:00", exif={"make": None, "model": None} | GPS),
        "unknown": add(taken="2024-05-04T09:05:00", exif={"make": None, "model": None}),
    }
    sync(signed_in)
    # The gallery knows the photos by its own ids: name them by file.
    return {
        name: fake_immich.assets[immich_id]["originalFileName"] for name, immich_id in ids.items()
    }


def items(client: TestClient, **params: Any) -> dict[str, dict[str, Any]]:
    response = client.get("/api/assets", params={"month": "2024-05", **params})
    assert response.status_code == 200
    return {item["file_name"]: item for item in response.json()}


def test_marks_by_the_same_camera_or_another(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    nearby = {
        name: items(signed_in)[asset_id]["nearby"]
        for name, asset_id in library.items()
        if asset_id in items(signed_in)
    }

    assert nearby["canon_10min"] == "same_camera"
    assert nearby["canon_after_phone"] == "other_camera"
    assert nearby["canon_20min"] is None
    assert nearby["scan"] is None
    assert nearby["after_scan"] is None
    assert nearby["unknown"] == "other_camera"
    # Located photos are never marked.
    assert nearby["canon_gps"] is None
    assert nearby["phone_gps"] is None
    if "after_trashed" in nearby:
        assert nearby["after_trashed"] is None


def test_the_same_camera_wins_over_another(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    fake_immich.add_asset(taken="2024-05-01T14:15:00", exif=CANON | GPS)
    sync(signed_in, full=True)
    assert items(signed_in)[library["canon_after_phone"]]["nearby"] == "same_camera"
    # 14:20 is now 5 min after a located Canon photo.
    assert items(signed_in)[library["canon_20min"]]["nearby"] == "same_camera"


def test_filter_and_month_counts(signed_in: TestClient, library: dict[str, str]) -> None:
    filtered = items(signed_in, nearby="true")
    assert set(filtered) == {
        library["canon_10min"],
        library["canon_after_phone"],
        library["unknown"],
    }
    months = signed_in.get("/api/assets/months", params={"nearby": "true"}).json()
    assert months == [{"month": "2024-05", "count": 3}]


def test_the_window_is_a_setting(signed_in: TestClient, library: dict[str, str]) -> None:
    signed_in.app.state.settings.time_neighbors_nearby_minutes = 30  # type: ignore[attr-defined]
    assert items(signed_in)[library["canon_20min"]]["nearby"] == "other_camera"
    options = signed_in.get("/api/assets/filter-options").json()
    assert options["nearby_minutes"] == 30
