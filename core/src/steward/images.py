# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cutting the part of a photo the user selected, for module runs on it (FR-35)."""

import io
from collections.abc import Mapping

from PIL import Image, ImageOps

# The long side of the cut part at most: as big as the preview of a whole photo.
MAX_SIDE = 1440
JPEG_QUALITY = 92


class UnreadableImage(Exception):
    """The image cannot be decoded."""


def crop(content: bytes, region: Mapping[str, float]) -> bytes:
    """The part of the image as a JPEG. `region` has x, y, w, h as shares of the width and
    height of the photo as shown, i.e. turned by its EXIF data."""
    try:
        with Image.open(io.BytesIO(content)) as image:
            # Originals keep their orientation in EXIF; the part was chosen on the turned photo.
            turned = ImageOps.exif_transpose(image)
            width, height = turned.size
            box = (
                round(region["x"] * width),
                round(region["y"] * height),
                round((region["x"] + region["w"]) * width),
                round((region["y"] + region["h"]) * height),
            )
            part = turned.crop(box).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise UnreadableImage(str(exc)) from exc
    part.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    part.save(out, "JPEG", quality=JPEG_QUALITY)
    return out.getvalue()
