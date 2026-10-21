# SPDX-License-Identifier: AGPL-3.0-or-later
"""Photos turned in the app: shown turned, and modules run on them turned."""

import io
from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient
from PIL import Image
from test_module_runs import geoclip, start_worker
from test_regions import LEFT_HALF, color_of, is_red, lease, photo, two_colors

from steward import rotation
from steward.images import crop, turned
from steward.rotation import with_turn

__all__ = ["photo"]  # a fixture, used by name

TOP_HALF = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.5}


def is_blue(content: bytes) -> bool:
    r, _, b = color_of(content)
    return b > 200 and r < 60


def test_turning_is_clockwise() -> None:
    # Red left half: turned 90° clockwise it is on top, 270° at the bottom.
    assert is_red(crop(turned(two_colors(), 90), TOP_HALF))
    assert is_blue(crop(turned(two_colors(), 270), TOP_HALF))
    assert is_blue(crop(turned(two_colors(), 180), LEFT_HALF))
    with Image.open(io.BytesIO(turned(two_colors((400, 200)), 90))) as image:
        assert image.size == (200, 400)


def test_part_is_cut_from_the_turned_photo() -> None:
    assert is_red(crop(two_colors(), TOP_HALF, turn=90))
    assert is_blue(crop(two_colors(), TOP_HALF, turn=270))


def test_thumbnail_turned(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str]
) -> None:
    asset, immich_id = photo
    fake_immich.previews[immich_id] = two_colors()
    response = signed_in.get(
        f"/api/assets/{asset}/thumbnail", params={"size": "preview", "turn": 90}
    )
    assert response.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (200, 400)
    assert is_red(crop(response.content, TOP_HALF))
    # Cached apart from the photo as it is.
    plain = signed_in.get(f"/api/assets/{asset}/thumbnail", params={"size": "preview"})
    assert plain.headers["etag"] != response.headers["etag"]
    bad = signed_in.get(f"/api/assets/{asset}/thumbnail", params={"turn": 45})
    assert bad.status_code == 422


def run_turned(
    client: TestClient, asset: str, turn: int, region: dict[str, float] | None = None
) -> Any:
    body: dict[str, Any] = {"turn": turn} | ({"region": region} if region else {})
    return client.post(f"/api/assets/{asset}/modules/geoclip/run", json=body)


def test_module_gets_the_photo_turned(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str]
) -> None:
    asset, immich_id = photo
    fake_immich.previews[immich_id] = two_colors()
    worker = start_worker(signed_in)
    run_turned(signed_in, asset, 180)
    # Turned again before a worker took it: the newest turn counts.
    run_turned(signed_in, asset, 90)
    assert geoclip(signed_in, asset)["turn"] == 90

    job = lease(signed_in, worker)
    image = signed_in.get(f"/api/worker/jobs/{job['job_id']}/image", headers=worker)
    assert image.headers["content-type"] == "image/jpeg"
    assert is_red(crop(image.content, TOP_HALF))


def test_part_of_the_turned_photo(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str]
) -> None:
    asset, immich_id = photo
    fake_immich.previews[immich_id] = two_colors()
    worker = start_worker(signed_in)
    run_turned(signed_in, asset, 270, TOP_HALF)
    job = lease(signed_in, worker)
    image = signed_in.get(f"/api/worker/jobs/{job['job_id']}/image", headers=worker)
    assert is_blue(image.content)
    blocks = signed_in.get(f"/api/assets/{asset}/suggestions").json()
    part = next(b for b in blocks if b["key"] == "geoclip:region")
    assert (part["turn"], part["region"]) == (270, TOP_HALF)


@pytest.mark.parametrize("turn", [45, -90, 360])
def test_only_quarter_turns(signed_in: TestClient, photo: tuple[str, str], turn: int) -> None:
    assert run_turned(signed_in, photo[0], turn).status_code == 422


ROTATE_90 = {"action": "rotate", "parameters": {"angle": 90}}
CROP = {"action": "crop", "parameters": {"x": 0, "y": 0, "width": 100, "height": 50}}
MIRROR = {"action": "mirror", "parameters": {"axis": "horizontal"}}


def rotate(angle: int) -> dict[str, Any]:
    return {"action": "rotate", "parameters": {"angle": angle}}


def test_turn_goes_into_the_edits() -> None:
    assert with_turn([], 90) == [ROTATE_90]
    # Other edits stay as they are; a new rotation goes last (onto the photo as shown).
    assert with_turn([CROP, MIRROR], 270) == [CROP, MIRROR, rotate(270)]
    # One rotation at most: the turn adds to it, and a full circle removes it.
    assert with_turn([CROP, ROTATE_90], 90) == [CROP, rotate(180)]
    assert with_turn([CROP, ROTATE_90], 270) == [CROP]
    # A mirror after the rotation turns it the other way round.
    assert with_turn([ROTATE_90, MIRROR], 90) == [MIRROR]
    assert with_turn([rotate(180), MIRROR], 90) == [ROTATE_90, MIRROR]
    # Immich's own ids are not sent back.
    assert with_turn([ROTATE_90 | {"id": "x"}], 180) == [rotate(270)]


def save_rotation(client: TestClient, asset: str, turn: int) -> Any:
    return client.post(f"/api/assets/{asset}/rotate", json={"turn": turn})


@pytest.fixture
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rotation, "THUMBNAIL_POLL_S", 0.0)


def test_rotation_saved_in_immich(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str], fast_polling: None
) -> None:
    asset, immich_id = photo
    fake_immich.edits[immich_id] = [CROP]
    worker = start_worker(signed_in)
    signed_in.post(f"/api/assets/{asset}/modules/geoclip/run")
    job = lease(signed_in, worker)
    result = {"module_version": "1", "candidates": []}
    signed_in.post(f"/api/worker/jobs/{job['job_id']}/result", json=result, headers=worker)
    assert geoclip(signed_in, asset)["status"] == "done"
    version = signed_in.get(f"/api/assets/{asset}").json()["version"]

    detail = save_rotation(signed_in, asset, 90)
    assert detail.status_code == 200
    assert fake_immich.edits[immich_id] == [CROP, ROTATE_90]
    # New thumbnails: new addresses, and the module looks at the photo again.
    assert detail.json()["version"] != version
    assert geoclip(signed_in, asset)["status"] == "not_run"

    # Turned back: the rotation goes, the crop stays.
    save_rotation(signed_in, asset, 270)
    assert fake_immich.edits[immich_id] == [CROP]


def test_rotation_back_to_none_removes_the_edits(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str], fast_polling: None
) -> None:
    asset, immich_id = photo
    fake_immich.edits[immich_id] = [rotate(180)]
    assert save_rotation(signed_in, asset, 180).status_code == 200
    assert immich_id not in fake_immich.edits


def test_slow_thumbnails_are_left_to_the_sync(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str], fast_polling: None
) -> None:
    asset, immich_id = photo
    fake_immich.edit_thumbnails_late = True
    assert save_rotation(signed_in, asset, 90).status_code == 200
    assert fake_immich.edits[immich_id] == [ROTATE_90]


def test_rotation_needs_the_edit_permissions(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str]
) -> None:
    fake_immich.can_edit = False
    response = save_rotation(signed_in, photo[0], 90)
    assert (response.status_code, response.json()["code"]) == (403, "immich_missing_permissions")
    assert "asset.edit.create" in response.json()["params"]["permissions"]


def test_videos_cannot_be_rotated_in_immich(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str]
) -> None:
    asset, immich_id = photo
    fake_immich.assets[immich_id]["type"] = "VIDEO"
    sync(signed_in, full=True)
    response = save_rotation(signed_in, asset, 90)
    assert (response.status_code, response.json()["code"]) == (422, "rotate_not_supported")
    assert save_rotation(signed_in, asset, 45).status_code == 422
