# SPDX-License-Identifier: AGPL-3.0-or-later
"""Photos as the user sees them in the app: turned by hand, or a part selected (FR-35)."""

import io
from collections.abc import Mapping

from PIL import Image, ImageOps

# The long side of the cut part at most: as big as the preview of a whole photo.
MAX_SIDE = 1440
# The long side of a turned photo shown in full size.
MAX_TURNED_SIDE = 4096
JPEG_QUALITY = 92

# Turns the user can give a photo, clockwise in degrees.
TURNS = (0, 90, 180, 270)
_TRANSPOSE = {
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


class UnreadableImage(Exception):
    """The image cannot be decoded."""


def crop(content: bytes, region: Mapping[str, float], turn: int = 0) -> bytes:
    """The part of the image as a JPEG. `region` has x, y, w, h as shares of the width and
    height of the photo as shown: turned by its EXIF data, then by `turn` degrees clockwise."""
    with _opened(content, turn) as photo:
        width, height = photo.size
        box = (
            round(region["x"] * width),
            round(region["y"] * height),
            round((region["x"] + region["w"]) * width),
            round((region["y"] + region["h"]) * height),
        )
        part = photo.crop(box)
    return _jpeg(part, MAX_SIDE)


def turned(content: bytes, turn: int, max_side: int = MAX_TURNED_SIDE) -> bytes:
    """The whole image turned by `turn` degrees clockwise, as a JPEG."""
    with _opened(content, turn) as photo:
        return _jpeg(photo, max_side)


def _opened(content: bytes, turn: int) -> Image.Image:
    try:
        with Image.open(io.BytesIO(content)) as image:
            # Originals keep their orientation in EXIF; the user sees the photo turned by it.
            photo = ImageOps.exif_transpose(image).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise UnreadableImage(str(exc)) from exc
    if turn in _TRANSPOSE:
        return photo.transpose(_TRANSPOSE[turn])
    return photo


def _jpeg(image: Image.Image, max_side: int) -> bytes:
    image.thumbnail((max_side, max_side))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=JPEG_QUALITY)
    return out.getvalue()
