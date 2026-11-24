# SPDX-License-Identifier: AGPL-3.0-or-later
"""The street module (D-244, D-245): panorama views, and the way the photo looks."""

import io
from typing import Any

import numpy as np
import pytest
from PIL import Image

from steward_worker.modules.geoclip import ModuleOptions
from steward_worker.modules.street import (
    PANO_VIEWS,
    StreetModule,
    _angles,
    _offset,
    pano_views,
    photo_fov,
    view_to_pano,
)


def jpeg(width: int, height: int, color: tuple[int, int, int] = (90, 120, 150)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, "JPEG")
    return out.getvalue()


def test_views_of_a_panorama() -> None:
    # A panorama with a red stripe in its middle and a blue one a quarter to the right.
    pano = np.zeros((200, 400, 3), dtype=np.uint8)
    pano[:, 198:202] = (255, 0, 0)
    pano[:, 298:302] = (0, 0, 255)
    views = pano_views(Image.fromarray(pano))
    assert len(views) == PANO_VIEWS
    middle = np.asarray(views[0])[:, 320]
    right = np.asarray(views[2])[:, 320]
    assert middle[:, 0].mean() > 200 and right[:, 2].mean() > 200
    # The middle of a view is the middle of its part of the panorama.
    assert view_to_pano(0.5, 0.5, 0) == pytest.approx((0.5, 0.5))
    assert view_to_pano(0.5, 0.5, 2) == pytest.approx((0.75, 0.5))
    assert view_to_pano(0.5, 0.5, 6) == pytest.approx((0.25, 0.5))


def test_angles_across_an_image() -> None:
    assert _angles([0.5], 70)[0] == pytest.approx(0)
    assert _angles([1.0], 70)[0] == pytest.approx(35)
    assert _angles([0.0], 70)[0] == pytest.approx(-35)


class FakeSimilar:
    """Vectors by the color of an image: the photo is grey-blue, alike images are too."""

    def vectors(self, images: list[Any]) -> Any:
        return np.array([np.asarray(i).reshape(-1, 3).mean(axis=0) for i in images])


class FakeDetails:
    """Points of a scene seen 20 degrees further left in the image than in the photo: the photo
    looks 20 degrees to the left of the image."""

    def features_of(self, rgb: Any) -> dict[str, Any]:
        return {"image_size": np.array([[1000, 750]])}

    def match_points(self, first: Any, second: Any) -> tuple[Any, Any, Any]:
        xs = np.linspace(0.3, 0.7, 40)
        half_photo, half_image = np.tan(np.radians(32.5)), np.tan(np.radians(35))
        photo_angles = np.degrees(np.arctan((xs * 2 - 1) * half_photo))
        image_x = (np.tan(np.radians(photo_angles - 20)) / half_image + 1) / 2
        a = np.stack([xs * 1000, np.full(40, 300.0)], axis=1)
        b = np.stack([image_x * 1000, np.full(40, 300.0)], axis=1)
        return a, b, np.ones(40, dtype=bool)


def test_alike_first_and_the_way_the_photo_looks() -> None:
    module = StreetModule(ModuleOptions(device="cpu", threads=1))
    module._similar = FakeSimilar()  # type: ignore[assignment]
    module._details = FakeDetails()  # type: ignore[assignment]
    photo = jpeg(400, 300, (90, 120, 150))
    alike, other, unreadable = jpeg(400, 300, (92, 120, 148)), jpeg(400, 300, (250, 20, 10)), b"x"
    results = module.compare(photo, [other, alike, unreadable])
    assert results[2] is None
    found_other, found_alike = results[0], results[1]
    assert found_other is not None and found_alike is not None
    assert found_alike.similarity > found_other.similarity
    assert found_alike.checked and found_alike.inliers == 40 and found_alike.lines
    assert found_alike.offset == pytest.approx(-20, abs=0.5)
    assert found_alike.spread == pytest.approx(0, abs=0.5)
    assert found_alike.fov == 65


def test_the_width_of_view_of_the_photo_is_found() -> None:
    # The points of a photo taken with 50 degrees across: under the 65 assumed they spread.
    xs = np.linspace(0.05, 0.95, 60)
    photo_angles = np.degrees(np.arctan((xs * 2 - 1) * np.tan(np.radians(25))))
    image_angles = photo_angles + 30
    assert photo_fov([(xs, image_angles, 60)]) == pytest.approx(50)
    offset, spread = _offset(xs, image_angles, 50)
    assert offset == pytest.approx(30, abs=0.1) and spread == pytest.approx(0, abs=0.1)
    # Points near the middle tell nothing about the width: the assumed one stays.
    middle = np.linspace(0.48, 0.52, 30)
    near = np.degrees(np.arctan((middle * 2 - 1) * np.tan(np.radians(25))))
    assert photo_fov([(middle, near + np.random.default_rng(1).normal(0, 2, 30), 30)]) == 65
    assert photo_fov([]) == 65
