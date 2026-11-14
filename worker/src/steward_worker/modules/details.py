# SPDX-License-Identifier: AGPL-3.0-or-later
"""Matching details: do two photos show the same scene, point by point.

"Similar photos" (MegaLoc) compares the overall look, and two streets of one town may look alike.
This module looks closer: ALIKED (BSD-3-Clause) finds up to two thousand distinctive points in
each photo, LightGlue (Apache-2.0) pairs them up, and `geometry_inliers` keeps the pairs that fit
one geometry, as points of one rigid scene seen from two places do. A hundred such pairs hardly
happen by chance; a dozen happen between any two photos.

It does not suggest places by itself: the core asks it about a photo and the candidates of
another module, and marks the candidates it confirms.

Needs the extras `details` and `cpu` or `cuda`. On first use the weights (~50 MB) are downloaded
from GitHub into the cache of PyTorch (TORCH_HOME) and checked against their SHA-256.
"""

import gc
import hashlib
import io
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from steward_worker.modules.base import IMAGE_FORMATS, PairMatch, PermanentError
from steward_worker.modules.geoclip import ModuleOptions, resolve_device

log = logging.getLogger(__name__)

# File name in the cache of PyTorch (the names the model code looks for) -> pinned address, SHA-256.
WEIGHTS = {
    "aliked-n16.pth": (
        "https://github.com/Shiaoming/ALIKED/raw/683d7c65197395c0b3f01ebe76e1084a27e73a65/models/aliked-n16.pth",
        "5be8704840ed662d9d8c561bf7279c222092674e7eb05fd0feab94899e9d82f2",
    ),
    "aliked_lightglue_v0-1_arxiv.pth": (
        "https://github.com/cvg/LightGlue/releases/download/v0.1_arxiv/aliked_lightglue.pth",
        "d975e965b105311a6143194852297dff4f02aea5cc2e10cecfed966ca0e22503",
    ),
}
# The longer side the photos are compared at, and the points taken from each: the values the
# thresholds of the core were measured with.
SIDE = 1024
MAX_KEYPOINTS = 2048
# Matched pairs returned for drawing; the count is returned in full.
MAX_LINES = 80


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class DetailsModule:
    id = "details"
    # Bump when the weights, the size or the geometry check change: the counts stop being
    # comparable.
    version = "1"

    def __init__(self, options: ModuleOptions) -> None:
        self._options = options
        self._device = resolve_device(options.device)
        self._extractor: Any = None
        self._matcher: Any = None

    @staticmethod
    def _weights_dir() -> Path:
        import torch

        return Path(torch.hub.get_dir()) / "checkpoints"

    def weights_cached(self) -> bool:
        return all((self._weights_dir() / name).is_file() for name in WEIGHTS)

    def _ensure_weights(self) -> None:
        import torch

        folder = self._weights_dir()
        folder.mkdir(parents=True, exist_ok=True)
        for name, (url, digest) in WEIGHTS.items():
            path = folder / name
            if path.is_file() and sha256(path) == digest:
                continue
            # Checks the SHA-256 itself and leaves no file behind when it differs.
            torch.hub.download_url_to_file(url, str(path), hash_prefix=digest, progress=False)

    def load(self) -> None:
        import torch

        from steward_worker.modules.aliked_model import ALIKED
        from steward_worker.modules.lightglue_model import LightGlue

        torch.set_num_threads(self._options.threads)
        self._ensure_weights()
        # Both find their weights in the cache by file name and download nothing.
        extractor = ALIKED(max_num_keypoints=MAX_KEYPOINTS)  # type: ignore[no-untyped-call]
        self._extractor = extractor.eval().to(self._device)
        self._matcher = LightGlue(features="aliked").eval().to(self._device)
        log.info(
            "ALIKED and LightGlue loaded on %s with %d threads", self._device, self._options.threads
        )

    def unload(self) -> None:
        self._extractor = None
        self._matcher = None
        gc.collect()
        if self._device == "cuda":
            import torch

            torch.cuda.empty_cache()

    def features(self, image: bytes) -> dict[str, Any]:
        """The distinctive points of a photo, in the pixels of its copy SIDE long."""
        import torch
        import torchvision.transforms.functional as tfm
        from PIL import Image, UnidentifiedImageError

        assert self._extractor is not None, "load() first"
        try:
            with Image.open(io.BytesIO(image), formats=IMAGE_FORMATS) as opened:
                rgb = opened.convert("RGB")
                scale = SIDE / max(rgb.size)
                size = (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale)))
                rgb = rgb.resize(size, Image.Resampling.BILINEAR)
        except (UnidentifiedImageError, OSError) as exc:
            raise PermanentError(f"cannot read the image: {exc}") from exc
        with torch.inference_mode():
            found: dict[str, Any] = self._extractor.extract(tfm.to_tensor(rgb).to(self._device))
        return found

    def match(self, first: dict[str, Any], second: dict[str, Any]) -> PairMatch:
        import torch

        from steward_worker.modules.geometry import geometry_inliers

        assert self._matcher is not None, "load() first"
        with torch.inference_mode():
            pairs = self._matcher({"image0": first, "image1": second})["matches"][0]
        a = first["keypoints"][0][pairs[:, 0]].cpu().numpy()
        b = second["keypoints"][0][pairs[:, 1]].cpu().numpy()
        agree = geometry_inliers(a, b)
        wa, ha = first["image_size"][0].tolist()
        wb, hb = second["image_size"][0].tolist()
        lines = [
            (float(xa / wa), float(ya / ha), float(xb / wb), float(yb / hb))
            for (xa, ya), (xb, yb) in zip(a[agree][:MAX_LINES], b[agree][:MAX_LINES], strict=True)
        ]
        return PairMatch(matches=len(pairs), inliers=int(agree.sum()), lines=lines)

    def compare(self, image: bytes, others: Sequence[bytes]) -> list[PairMatch | None]:
        """The photo against each of the others; None where the other photo cannot be read."""
        photo = self.features(image)
        results: list[PairMatch | None] = []
        for other in others:
            try:
                results.append(self.match(photo, self.features(other)))
            except PermanentError:
                results.append(None)
        return results
