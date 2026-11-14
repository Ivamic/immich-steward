# SPDX-License-Identifier: AGPL-3.0-or-later
"""What aliked_model.py needs from its package, without kornia and OpenCV.

The base class of the extractor and the resizing follow lightglue/utils.py of
https://github.com/cvg/LightGlue (Apache License 2.0), rewritten with plain PyTorch.
"""

from types import SimpleNamespace
from typing import Any, ClassVar

import torch
import torch.nn.functional as F


def grayscale_to_rgb(image: Any) -> Any:
    return image.repeat(1, 3, 1, 1)


class ImagePreprocessor:
    """Resizes an image so that its longer side has `resize` pixels (larger or smaller)."""

    def __init__(self, resize: int | None = None, **_: Any) -> None:
        self.resize = resize

    def __call__(self, image: Any) -> tuple[Any, Any]:
        height, width = image.shape[-2:]
        if self.resize is not None:
            scale = self.resize / max(height, width)
            size = (max(1, round(height * scale)), max(1, round(width * scale)))
            image = F.interpolate(image, size=size, mode="bilinear", antialias=True)
        scales = torch.tensor([image.shape[-1] / width, image.shape[-2] / height]).to(image)
        return image, scales


class Extractor(torch.nn.Module):  # type: ignore[misc]
    default_conf: ClassVar[dict[str, Any]] = {}
    preprocess_conf: ClassVar[dict[str, Any]] = {}

    def __init__(self, **conf: Any) -> None:
        super().__init__()
        self.conf = SimpleNamespace(**{**self.default_conf, **conf})

    # Keypoints are given for pixel centers, as in the published weights.
    coords_offset = 0.0

    @torch.no_grad()  # type: ignore[untyped-decorator]
    def extract(self, image: Any, **conf: Any) -> dict[str, Any]:
        """Keypoints of one image (3 x H x W, values 0..1), in the pixels of that image."""
        if image.dim() == 3:
            image = image[None]
        shape = image.shape[-2:][::-1]
        image, scales = ImagePreprocessor(**{**self.preprocess_conf, **conf})(image)
        features: dict[str, Any] = self.forward({"image": image})
        features["image_size"] = torch.tensor(shape)[None].to(image).float()
        features["keypoints"] = (features["keypoints"] + 0.5) / scales[None] - 0.5
        return features
