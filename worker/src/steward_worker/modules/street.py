# SPDX-License-Identifier: AGPL-3.0-or-later
"""Street-level images against the photo (0.14, D-244, D-245): which of the images the user
was shown near a point look most like the photo, and which show the very same scene.

The core names the images (Mapillary, Panoramax) and hands them over itself; the worker never
reaches the providers. MegaLoc (as "similar photos") ranks them by how alike they look; a 360
degree panorama is cut into views around the horizon first, and its best view counts. The most
alike are then matched point by point with ALIKED and LightGlue (as "matching details"). From
the points that fit, the module also tells which way the photo looks compared with the image:
the points seen in both lie at the same bearing from two cameras close to each other. The width
of view of the photo is not known (Immich tells no 35 mm focal length): it is the one under which
the points of all images agree best, a panorama counting most, as its angles are known exactly.

Needs the extras `street` and `cpu` or `cuda`; uses the weights of both modules above.
"""

import io
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from steward_worker.modules.base import IMAGE_FORMATS, PermanentError, StreetMatch
from steward_worker.modules.details import DetailsModule
from steward_worker.modules.geoclip import ModuleOptions
from steward_worker.modules.similar import SimilarModule

log = logging.getLogger(__name__)

# A panorama (equirectangular) is about twice as wide as high.
PANO_RATIO = 1.9
# Views cut from a panorama around the horizon, each this wide, this many pixels a side.
PANO_VIEWS = 8
PANO_FOV = 75.0
PANO_VIEW_SIDE = 640
# The most alike images matched point by point.
CHECKED = 10
# The width of view assumed for a photo and for an ordinary street-level image: neither tells
# its own here (a phone takes about 65-70 degrees, a dashcam more).
PHOTO_FOV = 65.0
IMAGE_FOV = 70.0
# The widths of view of the photo tried, from a short tele to a wide angle; the one found is
# kept only when the points agree clearly better under it than under PHOTO_FOV.
PHOTO_FOVS = range(40, 101)
FOV_GAIN = 0.85
# The part of the width of the photo the points of an image have to cover to tell its width.
FOV_SPAN = 0.4
# A panorama tells the width of view this many times better than an ordinary image.
PANO_WEIGHT = 3
# Fewer points that fit tell nothing about the direction.
OFFSET_FROM = 20


@dataclass
class _View:
    """What is compared: an ordinary image, or one view of a panorama."""

    rgb: Any
    # The panorama view: its index, and the panorama it was cut from (for the lines).
    view: int | None = None


@dataclass
class _Matched:
    """An image matched point by point, before the way the photo looks is worked out."""

    index: int
    view: _View
    similarity: float
    matches: int
    inliers: int
    lines: list[tuple[float, float, float, float]]
    # Of the points that fit (none when too few): across the photo (0..1), and degrees to the
    # right of the middle of the image.
    photo_x: Any
    image_angles: Any


class StreetModule:
    id = "street"
    # Bump when the views, the models or the way of matching change.
    version = "2"

    def __init__(self, options: ModuleOptions) -> None:
        self._similar = SimilarModule(options)
        self._details = DetailsModule(options)

    def load(self) -> None:
        self._similar.load()
        self._details.load()

    def unload(self) -> None:
        self._similar.unload()
        self._details.unload()

    def weights_cached(self) -> bool:
        return self._similar.weights_cached() and self._details.weights_cached()

    def compare(self, image: bytes, others: Sequence[bytes]) -> list[StreetMatch | None]:
        """The photo against each street-level image, in their order; None where an image cannot
        be read."""
        import numpy as np

        photo = _read(image)
        if photo is None:
            raise PermanentError("cannot read the photo")
        read: list[tuple[Any, list[_View]] | None] = []
        for other in others:
            rgb = _read(other)
            if rgb is None:
                read.append(None)
            elif rgb.width >= PANO_RATIO * rgb.height:
                views = pano_views(rgb)
                read.append((rgb, [_View(v, i) for i, v in enumerate(views)]))
            else:
                read.append((rgb, [_View(rgb)]))

        flat = [view for entry in read if entry for view in entry[1]]
        vectors = self._similar.vectors([photo, *(v.rgb for v in flat)])
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True).clip(1e-9)
        alike = vectors[1:] @ vectors[0]

        # The best view of each image, and how alike it is.
        best: list[tuple[float, _View] | None] = []
        at = 0
        for entry in read:
            if entry is None:
                best.append(None)
                continue
            scores = alike[at : at + len(entry[1])]
            at += len(entry[1])
            index = int(np.argmax(scores))
            best.append((float(scores[index]), entry[1][index]))

        order = sorted(
            (i for i, found in enumerate(best) if found),
            key=lambda i: -best[i][0],  # type: ignore[index]
        )
        checked = set(order[:CHECKED])
        photo_points = self._details.features_of(photo) if checked else None
        results: list[StreetMatch | None] = []
        matched: list[_Matched] = []
        for i, (entry, found) in enumerate(zip(read, best, strict=True)):
            if entry is None or found is None:
                results.append(None)
                continue
            similarity, view = found
            results.append(StreetMatch(matches=0, inliers=0, similarity=similarity, view=view.view))
            if i in checked:
                matched.append(self._match(i, photo_points, view, similarity))

        fov = photo_fov(
            [(m.photo_x, m.image_angles, _weight(m)) for m in matched if len(m.photo_x)]
        )
        for m in matched:
            offset = spread = None
            if len(m.photo_x):
                offset, spread = _offset(m.photo_x, m.image_angles, fov)
            results[m.index] = StreetMatch(
                matches=m.matches,
                inliers=m.inliers,
                lines=m.lines,
                similarity=m.similarity,
                checked=True,
                view=m.view.view,
                offset=offset,
                spread=spread,
                fov=fov if offset is not None else None,
            )
        return results

    def _match(self, index: int, photo_points: Any, view: _View, similarity: float) -> _Matched:
        import numpy as np

        other = self._details.features_of(view.rgb)
        a, b, agree = self._details.match_points(photo_points, other)
        wa, ha = photo_points["image_size"][0].tolist()
        wb, hb = other["image_size"][0].tolist()
        fitting = np.flatnonzero(agree)
        # Lines on the photo and on the image as shown: a panorama whole, not its view.
        shown = fitting[np.linspace(0, len(fitting) - 1, min(80, len(fitting))).round().astype(int)]
        lines = []
        for (xa, ya), (xb, yb) in zip(a[shown], b[shown], strict=True):
            if view.view is None:
                lines.append((float(xa / wa), float(ya / ha), float(xb / wb), float(yb / hb)))
            else:
                px, py = view_to_pano(float(xb / wb), float(yb / hb), view.view)
                lines.append((float(xa / wa), float(ya / ha), px, py))
        # Fewer points that fit tell nothing about the direction.
        told = fitting if len(fitting) >= OFFSET_FROM else fitting[:0]
        if view.view is None:
            image_angles = _angles(b[told, 0] / wb, IMAGE_FOV)
        else:
            image_angles = _angles(b[told, 0] / wb, PANO_FOV) + view.view * 360 / PANO_VIEWS
        return _Matched(
            index=index,
            view=view,
            similarity=similarity,
            matches=len(a),
            inliers=int(agree.sum()),
            lines=lines,
            photo_x=a[told, 0] / wa,
            image_angles=image_angles,
        )


def _weight(matched: _Matched) -> float:
    return len(matched.photo_x) * (PANO_WEIGHT if matched.view.view is not None else 1)


def _offset(photo_x: Any, image_angles: Any, fov: float) -> tuple[float, float]:
    """Degrees the photo looks to the right of the image, and how far the points spread around
    that."""
    import numpy as np

    differences = (image_angles - _angles(photo_x, fov) + 180) % 360 - 180
    offset = float(np.median(differences))
    return offset, float(np.median(np.abs(differences - offset)))


def photo_fov(images: Sequence[tuple[Any, Any, float]]) -> float:
    """The width of view of the photo under which the points of the images agree best (each
    image: across the photo, degrees to the right of the image, weight); PHOTO_FOV when none
    tells it clearly."""
    import numpy as np

    # Points near the middle only look alike under any width: such images do not count.
    images = [
        (x, angles, weight)
        for x, angles, weight in images
        if np.percentile(x, 90) - np.percentile(x, 10) >= FOV_SPAN
    ]
    if not images:
        return PHOTO_FOV
    total = sum(weight for _, _, weight in images)

    def disagreement(fov: float) -> float:
        return sum(weight * _offset(x, angles, fov)[1] for x, angles, weight in images) / total

    found = min(PHOTO_FOVS, key=disagreement)
    return float(found) if disagreement(found) < FOV_GAIN * disagreement(PHOTO_FOV) else PHOTO_FOV


def _read(image: bytes) -> Any:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(image), formats=IMAGE_FORMATS) as opened:
            return opened.convert("RGB")
    except (UnidentifiedImageError, OSError):
        return None


def _angles(xs: Any, fov: float) -> Any:
    """Degrees to the right of the middle of an image, for places across it (0..1)."""
    import numpy as np

    half = math.tan(math.radians(fov) / 2)
    return np.degrees(np.arctan((np.asarray(xs) * 2 - 1) * half))


def pano_views(pano: Any, views: int = PANO_VIEWS, fov: float = PANO_FOV) -> list[Any]:
    """Ordinary views cut from a 360-degree panorama around the horizon: the first looks at its
    middle, the next ones every 360/views degrees to the right."""
    import numpy as np
    from PIL import Image

    pixels = np.asarray(pano)
    height, width = pixels.shape[:2]
    span = math.tan(math.radians(fov) / 2)
    xs, ys = np.meshgrid(
        np.linspace(-span, span, PANO_VIEW_SIDE), np.linspace(-span, span, PANO_VIEW_SIDE)
    )
    lon = np.arctan2(xs, 1.0)
    lat = np.arctan2(-ys, np.sqrt(xs**2 + 1.0))
    rows = np.clip(((0.5 - lat / math.pi) * height).astype(int), 0, height - 1)
    out = []
    for view in range(views):
        yaw = 2 * math.pi * view / views
        cols = (((lon + yaw) / (2 * math.pi) + 0.5) * width).astype(int) % width
        out.append(Image.fromarray(pixels[rows, cols]))
    return out


def view_to_pano(x: float, y: float, view: int, fov: float = PANO_FOV) -> tuple[float, float]:
    """A place in a view (0..1 across and down) as a place in the panorama it was cut from."""
    span = math.tan(math.radians(fov) / 2)
    xs, ys = (2 * x - 1) * span, (2 * y - 1) * span
    lon = math.atan2(xs, 1.0) + 2 * math.pi * view / PANO_VIEWS
    lat = math.atan2(-ys, math.sqrt(xs**2 + 1.0))
    return ((lon / (2 * math.pi) + 0.5) % 1.0, 0.5 - lat / math.pi)
