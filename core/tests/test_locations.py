# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient

from steward import locations

KOTOR = {"latitude": 42.4247, "longitude": 18.7712}
BUDVA = {"latitude": 42.2864, "longitude": 18.84}
TAG = "steward/estimated"


@pytest.fixture(autouse=True)
def fast_clear_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locations, "CLEAR_POLL_S", 0.0)


@pytest.fixture
def photos(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, tuple[str, str]]:
    """Name -> (local id, Immich id)."""
    immich_ids = {
        "empty": fake_immich.add_asset(taken="2024-05-01T10:00:00"),
        "next": fake_immich.add_asset(taken="2024-05-01T09:00:00"),
        "located": fake_immich.add_asset(taken="2024-05-01T08:00:00", exif=BUDVA),
    }
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    by_name = {item["file_name"]: item["id"] for item in items}
    return {
        name: (by_name[fake_immich.assets[immich_id]["originalFileName"]], immich_id)
        for name, immich_id in immich_ids.items()
    }


def put_location(client: TestClient, asset_id: str, point: dict[str, float], **params: Any) -> Any:
    return client.put(f"/api/assets/{asset_id}/location", json=point, params=params)


def immich_point(fake_immich: FakeImmich, immich_id: str) -> tuple[float, float]:
    exif = fake_immich.assets[immich_id]["exifInfo"]
    return exif["latitude"], exif["longitude"]


def test_write_location_tags_and_records_history(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    local_id, immich_id = photos["empty"]
    response = put_location(signed_in, local_id, KOTOR, show="todo")
    assert response.status_code == 200
    detail = response.json()

    assert immich_point(fake_immich, immich_id) == (KOTOR["latitude"], KOTOR["longitude"])
    assert fake_immich.tag_values(immich_id) == {TAG}
    assert (detail["latitude"], detail["longitude"]) == (KOTOR["latitude"], KOTOR["longitude"])
    [change] = detail["location_history"]
    assert change["prev_latitude"] is None
    assert change["source"] == "manual"
    assert change["status"] == "applied"
    assert detail["can_undo"] is True
    # The photo has left the to-do list.
    todo = signed_in.get("/api/assets", params={"month": "2024-05", "show": "todo"}).json()
    assert local_id not in [item["id"] for item in todo]


def test_undo_over_empty_location_clears_it(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    local_id, immich_id = photos["empty"]
    put_location(signed_in, local_id, KOTOR)
    response = signed_in.post(f"/api/assets/{local_id}/location/undo")
    assert response.status_code == 200
    assert immich_point(fake_immich, immich_id) == (None, None)
    assert fake_immich.tag_values(immich_id) == set()
    assert response.json()["latitude"] is None
    todo = signed_in.get("/api/assets", params={"month": "2024-05", "show": "todo"}).json()
    assert local_id in [item["id"] for item in todo]


def test_undo_restores_our_point_when_immich_keeps_null_island(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    fake_immich.clears_null_island = False
    local_id, immich_id = photos["empty"]
    put_location(signed_in, local_id, KOTOR)
    response = signed_in.post(f"/api/assets/{local_id}/location/undo")
    assert response.status_code == 502
    assert response.json()["code"] == "location_clear_failed"
    assert immich_point(fake_immich, immich_id) == (KOTOR["latitude"], KOTOR["longitude"])
    detail = signed_in.get(f"/api/assets/{local_id}").json()
    assert detail["location_history"][0]["status"] == "applied"
    assert fake_immich.tag_values(immich_id) == {TAG}


def test_undo_restores_previous_location_and_keeps_existing_tag(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    local_id, immich_id = photos["located"]
    first = put_location(signed_in, local_id, KOTOR).json()
    assert first["location_history"][0]["prev_latitude"] == BUDVA["latitude"]
    assert first["can_undo"] is True
    second = put_location(signed_in, local_id, {"latitude": 42.0, "longitude": 19.0}).json()
    assert len(second["location_history"]) == 2

    # Undo goes back one write at a time; the tag stays while our coordinates stay.
    undone = signed_in.post(f"/api/assets/{local_id}/location/undo").json()
    assert immich_point(fake_immich, immich_id) == (KOTOR["latitude"], KOTOR["longitude"])
    assert fake_immich.tag_values(immich_id) == {TAG}
    assert [c["status"] for c in undone["location_history"]] == ["undone", "applied"]

    undone = signed_in.post(f"/api/assets/{local_id}/location/undo").json()
    assert immich_point(fake_immich, immich_id) == (BUDVA["latitude"], BUDVA["longitude"])
    assert fake_immich.tag_values(immich_id) == set()
    assert undone["latitude"] == BUDVA["latitude"]
    assert undone["can_undo"] is False  # both writes are undone

    response = signed_in.post(f"/api/assets/{local_id}/location/undo")
    assert response.status_code == 409
    assert response.json()["code"] == "location_nothing_to_undo"


def test_undo_refuses_when_location_changed_in_immich(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    local_id, immich_id = photos["located"]
    put_location(signed_in, local_id, KOTOR)
    fake_immich.assets[immich_id]["exifInfo"] |= {"latitude": 10.0, "longitude": 10.0}
    writes = fake_immich.location_writes

    response = signed_in.post(f"/api/assets/{local_id}/location/undo")
    assert response.status_code == 409
    assert response.json()["code"] == "location_changed_in_immich"
    assert fake_immich.location_writes == writes
    assert immich_point(fake_immich, immich_id) == (10.0, 10.0)


def test_tagging_failure_keeps_the_write(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    fake_immich.fail_tagging = True
    local_id, immich_id = photos["located"]
    response = put_location(signed_in, local_id, KOTOR)
    assert response.status_code == 200
    assert response.json()["location_history"][0]["status"] == "applied"
    assert immich_point(fake_immich, immich_id) == (KOTOR["latitude"], KOTOR["longitude"])


def test_skipped_photo_returns_to_new_after_write(
    signed_in: TestClient, photos: dict[str, tuple[str, str]]
) -> None:
    local_id, _ = photos["empty"]
    signed_in.put(f"/api/assets/{local_id}/review", json={"status": "skipped"})
    assert put_location(signed_in, local_id, KOTOR).json()["review_status"] == "new"


def test_location_validation_and_access(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    local_id, _ = photos["empty"]
    assert put_location(signed_in, local_id, {"latitude": 91, "longitude": 0}).status_code == 422
    # Immich takes exactly (0, 0) for "no location".
    null_island = put_location(signed_in, local_id, {"latitude": 0, "longitude": 0})
    assert null_island.json()["code"] == "location_null_island"
    assert put_location(signed_in, local_id, {"latitude": 0, "longitude": 18.0}).status_code == 200
    assert fake_immich.location_writes == 1
    missing = put_location(signed_in, "00000000-0000-4000-8000-000000000000", KOTOR)
    assert missing.status_code == 404
    assert fake_immich.location_writes == 1

    signed_in.post("/api/auth/logout")
    assert put_location(signed_in, local_id, KOTOR).status_code == 401
