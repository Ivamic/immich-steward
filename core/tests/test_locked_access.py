# SPDX-License-Identifier: AGPL-3.0-or-later
"""Images and writes of locked photos: through the session, only while the folder is open."""

from conftest import FakeImmich, run_jobs
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_locked_open import connected, open_with
from test_password_login import run_db

from steward.models import Asset

POINT = {"latitude": 45.4642, "longitude": 9.19}


def steward_id(client: TestClient, immich_id: str) -> str:
    return str(run_db(client, select(Asset.id).where(Asset.immich_id == immich_id)).scalar_one())


def with_locked(client: TestClient, fake: FakeImmich) -> tuple[str, str]:
    """A shown and a locked photo, synced with the folder open; returns their Steward ids."""
    shown = fake.add_asset()
    hidden = fake.add_asset(visibility="locked")
    connected(client, fake)
    open_with(client, "123456")
    run_jobs(client)
    return steward_id(client, shown), steward_id(client, hidden)


def test_a_locked_thumbnail_comes_through_the_session_and_is_not_kept(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    shown, hidden = with_locked(signed_in, fake_immich)
    asked = len(fake_immich.session_requests)
    response = signed_in.get(f"/api/assets/{hidden}/thumbnail")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "etag" not in response.headers
    assert fake_immich.session_requests[asked:] == [
        f"/api/assets/{fake_immich_id(signed_in, hidden)}/thumbnail"
    ]
    # Other photos still go with the API key and stay cached.
    response = signed_in.get(f"/api/assets/{shown}/thumbnail")
    assert response.status_code == 200
    assert "max-age" in response.headers["cache-control"]
    assert len(fake_immich.session_requests) == asked + 1


def fake_immich_id(client: TestClient, asset_id: str) -> str:
    return str(run_db(client, select(Asset.immich_id).where(Asset.id == asset_id)).scalar_one())


def test_a_closed_folder_shows_no_locked_image(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    _, hidden = with_locked(signed_in, fake_immich)
    signed_in.post("/api/locked/close")
    response = signed_in.get(f"/api/assets/{hidden}/thumbnail")
    assert response.status_code == 423
    assert response.json()["code"] == "locked_closed"


def test_a_locked_video_plays_while_open(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    fake_immich.add_asset(visibility="locked", type="VIDEO")
    connected(signed_in, fake_immich)
    open_with(signed_in, "123456")
    run_jobs(signed_in)
    [video] = run_db(signed_in, select(Asset.id).where(Asset.type == "VIDEO")).scalars().all()
    response = signed_in.get(f"/api/assets/{video}/video")
    assert response.status_code in (200, 206)
    assert response.headers["cache-control"] == "no-store"
    signed_in.post("/api/locked/close")
    assert signed_in.get(f"/api/assets/{video}/video").status_code == 423


def test_a_location_is_written_to_a_locked_photo_while_open(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    _, hidden = with_locked(signed_in, fake_immich)
    response = signed_in.put(f"/api/assets/{hidden}/location", json=POINT)
    assert response.status_code == 200
    exif = fake_immich.assets[fake_immich_id(signed_in, hidden)]["exifInfo"]
    assert (exif["latitude"], exif["longitude"]) == (POINT["latitude"], POINT["longitude"])
    assert signed_in.post(f"/api/assets/{hidden}/location/undo").status_code == 200

    signed_in.post("/api/locked/close")
    response = signed_in.put(f"/api/assets/{hidden}/location", json=POINT)
    assert response.status_code == 423


def test_several_photos_with_a_locked_one(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    shown, hidden = with_locked(signed_in, fake_immich)
    body = {"ids": [shown, hidden], **POINT, "overwrite": True}
    response = signed_in.post("/api/selection/location", json=body)
    assert response.status_code == 200
    assert response.json()["written"] == 2
    batch = response.json()["batch_id"]
    undone = signed_in.post("/api/selection/location/undo", json={"batch_id": batch})
    assert undone.json()["undone"] == 2

    signed_in.post("/api/locked/close")
    assert signed_in.post("/api/selection/location", json=body).status_code == 423
