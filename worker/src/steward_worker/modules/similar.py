# SPDX-License-Identifier: AGPL-3.0-or-later
"""M3: similar photos from the user's own library, by MegaLoc (MIT license).

MegaLoc turns a photo into a vector of 8448 numbers such that photos of the same place are close,
whatever the viewpoint, season or time of day. The worker only computes the vector; the core keeps
the vectors of the whole library and searches among the photos with a location.

Needs the extras `similar` and `cpu` or `cuda`. On first use the weights (~0.9 GB) are downloaded
from Hugging Face into its cache (HF_HOME).
"""

import gc
import io
import logging
import struct
from collections.abc import Sequence
from typing import Any

from steward_worker.modules.base import IMAGE_FORMATS, Embedding, PermanentError
from steward_worker.modules.geoclip import ModuleOptions, resolve_device

log = logging.getLogger(__name__)

WEIGHTS_REPO = "gberton/MegaLoc"
# Pinned: new weights would make new vectors incomparable with the stored ones, so they come
# only with a new module version.
WEIGHTS_REVISION = "a0f34722c4297ff787e022433799250180860af7"
DIM = 8448
# The input size of the MegaLoc paper; the photo is resized to it, aspect ratio ignored.
INPUT_SIZE = 322
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def pack(values: Sequence[float]) -> Embedding:
    """The vector as the core takes it: little-endian float16."""
    return Embedding(data=struct.pack(f"<{len(values)}e", *values), dim=len(values))


class SimilarModule:
    id = "similar"
    # Bump when the weights or the preprocessing change: stored vectors become incomparable.
    version = "1"

    def __init__(self, options: ModuleOptions) -> None:
        self._options = options
        self._device = resolve_device(options.device)
        self._model: Any = None

    def load(self) -> None:
        import torch
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file

        from steward_worker.modules.megaloc_model import MegaLoc

        torch.set_num_threads(self._options.threads)
        model = MegaLoc()
        path = hf_hub_download(WEIGHTS_REPO, "model.safetensors", revision=WEIGHTS_REVISION)
        model.load_state_dict(load_file(path))
        self._model = model.to(self._device).eval()
        log.info("MegaLoc loaded on %s with %d threads", self._device, self._options.threads)

    def weights_cached(self) -> bool:
        from huggingface_hub import try_to_load_from_cache

        path = try_to_load_from_cache(WEIGHTS_REPO, "model.safetensors", revision=WEIGHTS_REVISION)
        return isinstance(path, str)

    def unload(self) -> None:
        self._model = None
        gc.collect()
        if self._device == "cuda":
            import torch

            torch.cuda.empty_cache()

    def run(self, image: bytes) -> Embedding:
        import torch
        import torchvision.transforms.functional as tfm
        from PIL import Image, UnidentifiedImageError

        assert self._model is not None, "load() first"
        try:
            with Image.open(io.BytesIO(image), formats=IMAGE_FORMATS) as opened:
                rgb = opened.convert("RGB").resize(
                    (INPUT_SIZE, INPUT_SIZE), Image.Resampling.BICUBIC
                )
        except (UnidentifiedImageError, OSError) as exc:
            raise PermanentError(f"cannot read the image: {exc}") from exc
        pixels = tfm.normalize(tfm.to_tensor(rgb), IMAGENET_MEAN, IMAGENET_STD)
        with torch.inference_mode():
            vector = self._model(pixels.unsqueeze(0).to(self._device))[0]
        return pack(vector.float().cpu().tolist())
