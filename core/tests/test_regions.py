# SPDX-License-Identifier: AGPL-3.0-or-later
"""Module runs on a part of the photo the user selected (FR-35)."""

import io
from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient
from PIL import Image
from test_module_runs import geoclip, start_worker

from steward.images import UnreadableImage, crop

LEFT_HALF = {"x": 0.0, "y": 0.0, "w": 0.5, "h": 1.0}


def two_colors(size: tuple[int, int] = (400, 200), orientation: int | None = None) -> bytes:
    """Red left half, blue right half, as a JPEG; optionally with an EXIF orientation."""
    image = Image.new("RGB", size, "blue")
    image.paste("red", (0, 0, size[0] // 2, size[1]))
    out = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def color_of(content: bytes) -> tuple[int, int, int]:
    with Image.open(io.BytesIO(content)) as image:
        pixel = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
        assert isinstance(pixel, tuple)
        return int(pixel[0]), int(pixel[1]), int(pixel[2])


def is_red(content: bytes) -> bool:
    r, _, b = color_of(content)
    return r > 200 and b < 60


def test_crop_cuts_the_part() -> None:
    part = crop(two_colors(), LEFT_HALF)
    with Image.open(io.BytesIO(part)) as image:
        assert image.size == (200, 200)
    assert is_red(part)


def test_crop_follows_the_exif_orientation() -> None:
    # Orientation 6: shown turned by 90° clockwise, so the red half ends up on top.
    shown_top = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.5}
    assert is_red(crop(two_colors(orientation=6), shown_top))


def test_crop_keeps_parts_small_enough() -> None:
    with Image.open(io.BytesIO(crop(two_colors((4000, 1000)), LEFT_HALF))) as image:
        assert max(image.size) == 1440


def test_crop_refuses_what_is_no_image() -> None:
    with pytest.raises(UnreadableImage):
        crop(b"not an image", LEFT_HALF)


@pytest.fixture
def photo(signed_in: TestClient, fake_immich: FakeImmich) -> tuple[str, str]:
    """Local and Immich id of a photo without a location."""
    immich_id = fake_immich.add_asset(taken="2024-05-01T10:00:00", originalFileName="crowd.jpg")
    sync(signed_in)
    item = signed_in.get("/api/assets", params={"month": "2024-05"}).json()[0]
    return item["id"], immich_id


def run_on(client: TestClient, asset: str, region: dict[str, float] | None) -> Any:
    body = {"region": region} if region else None
    return client.post(f"/api/assets/{asset}/modules/geoclip/run", json=body)


def lease(client: TestClient, worker: dict[str, str]) -> dict[str, Any]:
    response = client.post("/api/worker/lease", json={"modules": ["geoclip"]}, headers=worker)
    job: dict[str, Any] = response.json()
    return job


def part_block(client: TestClient, asset: str) -> dict[str, Any]:
    blocks = client.get(f"/api/assets/{asset}/suggestions").json()
    block: dict[str, Any] = next(b for b in blocks if b["key"] == "geoclip:region")
    return block


def test_part_is_cut_from_the_original(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str]
) -> None:
    asset, immich_id = photo
    fake_immich.permissions.append("asset.download")
    fake_immich.originals[immich_id] = two_colors()
    worker = start_worker(signed_in)
    run_on(signed_in, asset, LEFT_HALF)
    block = part_block(signed_in, asset)
    assert (block["status"], block["region"]) == ("queued", LEFT_HALF)
    # The whole-photo block stays as it was.
    assert geoclip(signed_in, asset)["status"] == "not_run"

    job = lease(signed_in, worker)
    image = signed_in.get(f"/api/worker/jobs/{job['job_id']}/image", headers=worker)
    assert image.headers["content-type"] == "image/jpeg"
    assert is_red(image.content)


def test_part_falls_back_to_the_preview(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str]
) -> None:
    asset, immich_id = photo  # the API key may not download originals
    fake_immich.previews[immich_id] = two_colors()
    worker = start_worker(signed_in)
    run_on(signed_in, asset, {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0})
    job = lease(signed_in, worker)
    image = signed_in.get(f"/api/worker/jobs/{job['job_id']}/image", headers=worker)
    assert color_of(image.content)[2] > 200  # the blue half


def test_unreadable_photo_fails_the_part(signed_in: TestClient, photo: tuple[str, str]) -> None:
    asset, _ = photo  # the fake preview is no image
    worker = start_worker(signed_in)
    run_on(signed_in, asset, LEFT_HALF)
    job = lease(signed_in, worker)
    image = signed_in.get(f"/api/worker/jobs/{job['job_id']}/image", headers=worker)
    assert image.status_code == 410
    block = part_block(signed_in, asset)
    assert (block["status"], block["error_code"]) == ("failed", "image_invalid")
    # Failures on parts are not failures of the photo.
    assert signed_in.get("/api/library/workers").json()["failures"] == {}


def test_parts_stay_out_of_the_library_counts(
    signed_in: TestClient, photo: tuple[str, str]
) -> None:
    asset, _ = photo
    worker = start_worker(signed_in)
    run_on(signed_in, asset, LEFT_HALF)
    job = lease(signed_in, worker)
    result = {"module_version": "1", "candidates": [{"latitude": 1, "longitude": 2, "score": 0.9}]}
    signed_in.post(f"/api/worker/jobs/{job['job_id']}/result", json=result, headers=worker)
    assert part_block(signed_in, asset)["status"] == "done"
    assert signed_in.get("/api/library/workers").json()["runs"] == {}
    # A confident guess on a part does not mark the photo in the gallery.
    item = signed_in.get("/api/assets", params={"month": "2024-05"}).json()[0]
    assert item["geoclip_confident"] is False
    # The automatic runs still take the photo as a whole.
    runner = signed_in.app.state.job_runner  # type: ignore[attr-defined]
    signed_in.portal.call(runner.schedule_modules)  # type: ignore[union-attr]
    assert geoclip(signed_in, asset)["status"] == "queued"


def test_a_new_part_replaces_the_part_still_queued(
    signed_in: TestClient, photo: tuple[str, str]
) -> None:
    asset, _ = photo
    run_on(signed_in, asset, LEFT_HALF)
    other = {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5}
    blocks = run_on(signed_in, asset, other).json()
    parts = [b for b in blocks if b["key"] == "geoclip:region"]
    assert len(parts) == 1
    assert parts[0]["region"] == other


@pytest.mark.parametrize(
    "region",
    [
        {"x": 0.6, "y": 0.0, "w": 0.5, "h": 1.0},  # beyond the right edge
        {"x": 0.0, "y": 0.0, "w": 0.0, "h": 1.0},  # empty
        {"x": -0.1, "y": 0.0, "w": 0.5, "h": 1.0},
    ],
)
def test_parts_outside_the_photo_are_refused(
    signed_in: TestClient, photo: tuple[str, str], region: dict[str, float]
) -> None:
    assert run_on(signed_in, photo[0], region).status_code == 422


def test_part_of_a_video_is_cut_from_its_preview_frame(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    immich_id = fake_immich.add_asset(
        taken="2024-05-02T10:00:00", originalFileName="clip.mov", type="VIDEO"
    )
    fake_immich.permissions.append("asset.download")
    fake_immich.originals[immich_id] = b"a video file"  # not an image: must not be used
    fake_immich.previews[immich_id] = two_colors()
    sync(signed_in)
    item = signed_in.get("/api/assets", params={"month": "2024-05"}).json()[0]
    assert item["type"] == "VIDEO"
    worker = start_worker(signed_in)
    run_on(signed_in, item["id"], LEFT_HALF)
    job = lease(signed_in, worker)
    image = signed_in.get(f"/api/worker/jobs/{job['job_id']}/image", headers=worker)
    assert image.status_code == 200
    assert is_red(image.content)
