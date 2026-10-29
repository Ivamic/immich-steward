# SPDX-License-Identifier: AGPL-3.0-or-later
"""Playing videos from Immich through the app."""

import uuid

import pytest
from conftest import FakeImmich, sync, video_bytes
from fastapi.testclient import TestClient


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, tuple[str, str]]:
    """File name -> (id in the app, id in Immich)."""
    ids = {
        "clip.mp4": fake_immich.add_asset(
            taken="2024-05-01T10:00:00", originalFileName="clip.mp4", type="VIDEO"
        ),
        "photo.jpg": fake_immich.add_asset(
            taken="2024-05-01T11:00:00", originalFileName="photo.jpg"
        ),
    }
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    local = {item["file_name"]: item["id"] for item in items}
    return {name: (local[name], immich_id) for name, immich_id in ids.items()}


def test_the_whole_video(signed_in: TestClient, library: dict[str, tuple[str, str]]) -> None:
    local_id, immich_id = library["clip.mp4"]
    response = signed_in.get(f"/api/assets/{local_id}/video")

    assert response.status_code == 200
    assert response.content == video_bytes(immich_id)
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"


def test_a_part_for_seeking(signed_in: TestClient, library: dict[str, tuple[str, str]]) -> None:
    local_id, immich_id = library["clip.mp4"]
    response = signed_in.get(f"/api/assets/{local_id}/video", headers={"Range": "bytes=100-199"})

    whole = video_bytes(immich_id)
    assert response.status_code == 206
    assert response.content == whole[100:200]
    assert response.headers["content-range"] == f"bytes 100-199/{len(whole)}"
    assert response.headers["content-length"] == "100"


def test_only_videos_play(signed_in: TestClient, library: dict[str, tuple[str, str]]) -> None:
    local_id, _ = library["photo.jpg"]
    response = signed_in.get(f"/api/assets/{local_id}/video")
    assert response.status_code == 422
    assert response.json()["code"] == "not_a_video"


def test_missing_permission_is_told(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, tuple[str, str]]
) -> None:
    local_id, immich_id = library["clip.mp4"]
    fake_immich.video_status[immich_id] = 403
    response = signed_in.get(f"/api/assets/{local_id}/video")
    assert response.status_code == 403
    assert response.json()["code"] == "immich_missing_permissions"


def test_signed_out_gets_nothing(client: TestClient) -> None:
    assert client.get(f"/api/assets/{uuid.uuid4()}/video").status_code == 401
