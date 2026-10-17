# SPDX-License-Identifier: AGPL-3.0-or-later
"""M2: GeoCLIP, worldwide geolocation of a photo by a neural network (MIT license).

GeoCLIP scores 100 000 reference points around the world against the photo. The most probable
points are grouped into a few areas; each area is a candidate whose score is its total
probability and whose radius reflects how spread out its points are.

Needs the extras `geoclip` and `cpu` or `cuda`. On first use the CLIP ViT-L/14 backbone (~1.7 GB)
is downloaded from Hugging Face into its cache (HF_HOME).
"""

import gc
import io
import logging
from dataclasses import dataclass
from typing import Any

from steward_worker.modules.base import Candidate, PermanentError
from steward_worker.modules.clustering import cluster_points

log = logging.getLogger(__name__)

# Reference points taken into account per photo, and how they are grouped.
TOP_K = 200
JOIN_M = 25_000.0
MAX_CANDIDATES = 5
# Areas below this total probability are noise.
MIN_SCORE = 0.02
MIN_RADIUS_M = 5_000.0
MAX_RADIUS_M = 300_000.0


@dataclass(frozen=True)
class ModuleOptions:
    # CPU threads for PyTorch: keep low on a server shared with Immich (NFR-03).
    threads: int = 2
    # "cpu", "cuda" or "auto".
    device: str = "auto"


def resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


class GeoClipModule:
    id = "geoclip"
    # Bump when the model or the post-processing changes.
    version = "1"

    def __init__(self, options: ModuleOptions) -> None:
        self._options = options
        self._device = resolve_device(options.device)
        self._model: Any = None
        self._gallery: Any = None
        self._gallery_features: Any = None

    def load(self) -> None:
        import torch
        import torch.nn.functional as F
        from geoclip import GeoCLIP

        torch.set_num_threads(self._options.threads)
        model = GeoCLIP()
        # Only the image tower of CLIP is used; dropping the text tower saves ~0.5 GB.
        model.image_encoder.CLIP.text_model = torch.nn.Identity()
        model = model.to(self._device).eval()
        with torch.no_grad():
            # The reference points never change: encode them once, not for every photo.
            gallery = model.gps_gallery.to(self._device)
            self._gallery_features = F.normalize(model.location_encoder(gallery), dim=1)
        self._gallery = model.gps_gallery.cpu()
        self._model = model
        log.info("GeoCLIP loaded on %s with %d threads", self._device, self._options.threads)

    def unload(self) -> None:
        self._model = self._gallery = self._gallery_features = None
        gc.collect()
        if self._device == "cuda":
            import torch

            torch.cuda.empty_cache()

    def run(self, image: bytes) -> list[Candidate]:
        import torch
        import torch.nn.functional as F
        from PIL import Image, UnidentifiedImageError

        assert self._model is not None, "load() first"
        try:
            with Image.open(io.BytesIO(image)) as opened:
                pixels = self._model.image_encoder.preprocess_image(opened.convert("RGB"))
        except (UnidentifiedImageError, OSError) as exc:
            raise PermanentError(f"cannot read the image: {exc}") from exc

        with torch.no_grad():
            features = F.normalize(self._model.image_encoder(pixels.to(self._device)), dim=1)
            logits = self._model.logit_scale.exp() * features @ self._gallery_features.t()
            probs = logits.softmax(dim=-1)[0]
            top = torch.topk(probs, TOP_K)
        points = self._gallery.index_select(0, top.indices.cpu()).tolist()
        weights = top.values.cpu().tolist()
        return to_candidates([(p[0], p[1]) for p in points], weights)


def to_candidates(points: list[tuple[float, float]], weights: list[float]) -> list[Candidate]:
    candidates = []
    for cluster in cluster_points(points, weights, JOIN_M, MAX_CANDIDATES):
        if cluster.weight < MIN_SCORE:
            continue
        candidates.append(
            Candidate(
                latitude=round(cluster.latitude, 6),
                longitude=round(cluster.longitude, 6),
                score=round(min(cluster.weight, 1.0), 4),
                radius_m=round(min(max(2 * cluster.spread_m, MIN_RADIUS_M), MAX_RADIUS_M)),
                kind="area",
                evidence={"points": cluster.members},
            )
        )
    return candidates
