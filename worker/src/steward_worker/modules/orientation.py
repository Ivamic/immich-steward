# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turned photos (D-237): whether a photo is shown turned by 90, 180 or 270 degrees.

A 4-class EfficientNetV2-S by Duarte Barbosa (deep-image-orientation-detection, MIT license),
fine-tuned on COCO and other sets. The photo is looked at as Immich shows it; the answer is the
turn it has now: class 1 is turned 90 degrees counter-clockwise (it needs 90 clockwise), 2 is
upside down, 3 turned 90 degrees clockwise.

A photo the first look calls turned is looked at in its three other turns too, and the four
answers are added up: measured on 15 516 photos, this halves the upright photos taken for turned
(`_dev`, 2026-11-22). Most photos are upright, so this costs little.

Needs the extras `orientation` and `cpu` or `cuda`. On first use the weights (~80 MB) are
downloaded from Hugging Face into its cache (HF_HOME).
"""

import gc
import io
import logging
from typing import Any

from steward_worker.modules.base import IMAGE_FORMATS, Orientation, PermanentError
from steward_worker.modules.geoclip import ModuleOptions, resolve_device

log = logging.getLogger(__name__)

WEIGHTS_REPO = "DuarteBarbosa/deep-image-orientation-detection"
WEIGHTS_FILE = "orientation_model_v2_0.9882.pth"
# Pinned: other weights would give other answers, so they come only with a new module version.
WEIGHTS_REVISION = "9bc7687b9fd5152e220084ca23e13e7fa1daec38"
CLASSES = 4
# As the model was trained: squeezed to 416 x 416, the middle 384 x 384.
RESIZE = 416
INPUT_SIZE = 384
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
# A first answer "turned" at least this sure gets the look at the other three turns.
LOOK_AGAIN_FROM = 0.5


def combine(answers: list[list[float]]) -> list[float]:
    """The four looks as one answer: `answers[j]` is the answer for the photo turned by j more
    quarter turns counter-clockwise, so its class (r + j) % 4 speaks for the photo having turn r."""
    return [
        sum(answers[j][(turn + j) % CLASSES] for j in range(CLASSES)) / CLASSES
        for turn in range(CLASSES)
    ]


class OrientationModule:
    id = "orientation"
    # Bump when the weights, the preprocessing or the way of adding up the looks change.
    version = "1"

    def __init__(self, options: ModuleOptions) -> None:
        self._options = options
        self._device = resolve_device(options.device)
        self._model: Any = None

    def load(self) -> None:
        import torch
        from huggingface_hub import hf_hub_download
        from torch import nn
        from torchvision.models import efficientnet_v2_s

        torch.set_num_threads(self._options.threads)
        model = efficientnet_v2_s(weights=None)
        model.classifier = nn.Sequential(
            nn.Dropout(p=0.3, inplace=True),
            nn.Linear(model.classifier[1].in_features, CLASSES),
        )
        path = hf_hub_download(WEIGHTS_REPO, WEIGHTS_FILE, revision=WEIGHTS_REVISION)
        # Only tensors: a pickle with code in it is refused.
        state = torch.load(path, map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        self._model = model.to(self._device).eval()
        log.info(
            "orientation model loaded on %s with %d threads", self._device, self._options.threads
        )

    def weights_cached(self) -> bool:
        from huggingface_hub import try_to_load_from_cache

        path = try_to_load_from_cache(WEIGHTS_REPO, WEIGHTS_FILE, revision=WEIGHTS_REVISION)
        return isinstance(path, str)

    def unload(self) -> None:
        self._model = None
        gc.collect()
        if self._device == "cuda":
            import torch

            torch.cuda.empty_cache()

    def run(self, image: bytes) -> Orientation:
        import torch
        import torchvision.transforms.functional as tfm
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(io.BytesIO(image), formats=IMAGE_FORMATS) as opened:
                photo = opened.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise PermanentError(f"cannot read the image: {exc}") from exc

        def tensor(picture: Image.Image) -> Any:
            picture = picture.resize((RESIZE, RESIZE), Image.Resampling.BILINEAR)
            x = tfm.center_crop(tfm.to_tensor(picture), [INPUT_SIZE, INPUT_SIZE])
            return tfm.normalize(x, list(IMAGENET_MEAN), list(IMAGENET_STD))

        def look(pictures: list[Image.Image]) -> list[list[float]]:
            batch = torch.stack([tensor(p) for p in pictures]).to(self._device)
            with torch.inference_mode():
                probs = torch.softmax(self._model(batch).float(), dim=1)
            return [[float(v) for v in row] for row in probs.cpu()]

        [first] = look([photo])
        best = max(range(CLASSES), key=lambda c: first[c])
        if best == 0 or first[best] < LOOK_AGAIN_FROM:
            return Orientation(probs=tuple(first), looks=1)  # type: ignore[arg-type]
        turns = [
            Image.Transpose.ROTATE_90,
            Image.Transpose.ROTATE_180,
            Image.Transpose.ROTATE_270,
        ]
        others = look([photo.transpose(turn) for turn in turns])
        probs = combine([first, *others])
        return Orientation(probs=tuple(probs), looks=CLASSES)  # type: ignore[arg-type]
