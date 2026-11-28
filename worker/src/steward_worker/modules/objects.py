# SPDX-License-Identifier: AGPL-3.0-or-later
"""People, animals and vehicles in a photo (D-248): YOLO26s-seg of Ultralytics (AGPL-3.0, the code
and the weights), as a TorchScript export with NMS inside, run with plain PyTorch and torchvision.

Two uses:
- the module `objects` looks at every photo once and tells the core what is in it: the groups
  with their share of the photo, every object found, and a small label map to show the masks;
- the module `details` masks the groups the core asks for before matching the points of two
  photos (`mask_of`): points on a person or a dog seen on both photos are no sign of one place.

The image is fitted into 640 x 640 as Ultralytics does it, resized without antialiasing: with
the smoothing of Pillow the confidences move by a few hundredths and objects near the threshold
come and go (measured: the same objects as Ultralytics in 80 % of photos with Pillow, 98 % so).

Needs the extra `details` (or `objects`) and `cpu` or `cuda`. On first use the weights (~40 MB)
are downloaded from the releases of the app on GitHub into the cache of PyTorch and checked
against their SHA-256. `STEWARD_OBJECTS_WEIGHTS` names a local file instead (development).
"""

import gc
import io
import logging
import os
from pathlib import Path
from typing import Any

from steward_worker.modules.base import IMAGE_FORMATS, Objects, PermanentError
from steward_worker.modules.geoclip import ModuleOptions, resolve_device

log = logging.getLogger(__name__)

# Exported with `worker/tools/export_yolo26_seg.py` (torch 2.14.1, nms=True, imgsz=640) and
# published as a file of the release "models-1" of the app.
WEIGHTS_FILE = "yolo26s-seg.torchscript"
WEIGHTS_URL = (
    "https://github.com/Ivamic/immich-steward/releases/download/models-1/yolo26s-seg.torchscript"
)
WEIGHTS_SHA256 = "236ffd812e96b3576a63b60db75e7c3ec39e80c05e18aaabfe17a70b0bbe7f7b"
WEIGHTS_ENV = "STEWARD_OBJECTS_WEIGHTS"

# COCO classes by the group the settings offer.
GROUPS: dict[str, tuple[int, ...]] = {
    "person": (0,),
    # bird cat dog horse sheep cow elephant bear zebra giraffe
    "animal": (14, 15, 16, 17, 18, 19, 20, 21, 22, 23),
    # bicycle car motorcycle bus truck boat
    "vehicle": (1, 2, 3, 5, 7, 8),
}
# Values of the label map; 0 is nothing. One value per pixel: the surest object on top.
LABEL = {"person": 1, "animal": 2, "vehicle": 3}
GROUP_OF = {c: g for g, ids in GROUPS.items() for c in ids}
SIZE = 640
PAD = 114
CONF = 0.25
# The share of the photo is counted on a label map this long, the map kept this long.
COVER_SIDE = 256
KEEP_SIDE = 96


def weights_path() -> Path:
    local = os.environ.get(WEIGHTS_ENV, "").strip()
    if local:
        return Path(local)
    import torch

    return Path(torch.hub.get_dir()) / "checkpoints" / WEIGHTS_FILE


def ensure_weights() -> Path:
    import torch

    path = weights_path()
    if os.environ.get(WEIGHTS_ENV, "").strip():
        if not path.is_file():
            raise FileNotFoundError(f"{WEIGHTS_ENV}: no file {path}")
        return path
    if path.is_file():
        import hashlib

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest == WEIGHTS_SHA256:
            return path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Checks the SHA-256 itself and leaves no file behind when it differs.
    torch.hub.download_url_to_file(
        WEIGHTS_URL, str(path), hash_prefix=WEIGHTS_SHA256, progress=False
    )
    return path


class Segmenter:
    """YOLO26-seg from its TorchScript export: label maps of the groups at any size."""

    def __init__(self, device: str) -> None:
        import torch
        import torchvision  # noqa: F401  (registers torchvision::nms, which the export calls)

        self._torch = torch
        self.device = device
        self.model = torch.jit.load(str(ensure_weights()), map_location=device).eval()

    def _letterbox(self, rgb: Any) -> tuple[Any, int, int, int, int]:
        """The image as the model's input (1 x 3 x 640 x 640, 0..1), fitted as Ultralytics does:
        resized like cv2 INTER_LINEAR, padded with gray, the padding split as Ultralytics splits
        it. Done on the device: the image goes there once, as bytes."""
        import numpy as np
        import torch.nn.functional as F

        torch = self._torch
        w, h = rgb.size
        scale = min(SIZE / w, SIZE / h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        left, top = round((SIZE - nw) / 2 - 0.1), round((SIZE - nh) / 2 - 0.1)
        x = torch.from_numpy(np.asarray(rgb, dtype=np.uint8).copy()).to(self.device)
        x = x.permute(2, 0, 1)[None].float()
        if (nw, nh) != (w, h):
            x = F.interpolate(x, (nh, nw), mode="bilinear", align_corners=False, antialias=False)
            x = x.round().clamp(0, 255)
        x = F.pad(x, (left, SIZE - nw - left, top, SIZE - nh - top), value=float(PAD))
        return x / 255.0, left, top, nw, nh

    def labels(self, rgb: Any, size: tuple[int, int]) -> tuple[Any, list[dict[str, Any]]]:
        """The label map at `size` (width, height; uint8, see LABEL) and every object found:
        class, confidence and box in 0..1 of the image."""
        import numpy as np
        import torch.nn.functional as F

        torch = self._torch
        x, left, top, nw, nh = self._letterbox(rgb)
        out_w, out_h = size
        with torch.inference_mode():
            det, protos = self.model(x)
            det, protos = det[0].float(), protos[0].float()
            det = det[det[:, 4] >= CONF]
            found = [
                {
                    "class": int(d[5]),
                    "confidence": round(float(d[4]), 3),
                    "box": [
                        round(max(0.0, min(1.0, (float(d[0]) - left) / nw)), 4),
                        round(max(0.0, min(1.0, (float(d[1]) - top) / nh)), 4),
                        round(max(0.0, min(1.0, (float(d[2]) - left) / nw)), 4),
                        round(max(0.0, min(1.0, (float(d[3]) - top) / nh)), 4),
                    ],
                }
                for d in det
            ]
            out = np.zeros((out_h, out_w), dtype=np.uint8)
            wanted = [i for i, c in enumerate(det[:, 5].long().tolist()) if c in GROUP_OF]
            if not wanted:
                return out, found
            det = det[wanted]
            c, ph, pw = protos.shape
            masks = (det[:, 6:] @ protos.view(c, -1)).view(-1, ph, pw)
            masks = F.interpolate(masks[None], (SIZE, SIZE), mode="bilinear", align_corners=False)[
                0
            ]
            # Cut to the box (letterboxed pixels), then the padding off, then to the size asked.
            ys = torch.arange(SIZE, device=masks.device)[None, :, None]
            xs = torch.arange(SIZE, device=masks.device)[None, None, :]
            x1, y1, x2, y2 = (det[:, i, None, None] for i in range(4))
            masks = (masks > 0) & (xs >= x1) & (xs < x2) & (ys >= y1) & (ys < y2)
            masks = masks[:, top : top + nh, left : left + nw].float()
            masks = F.interpolate(masks[None], (out_h, out_w), mode="bilinear", align_corners=False)
            masks = (masks[0] > 0.5).cpu().numpy()
            for i in det[:, 4].argsort().tolist():  # the surest last, so on top
                out[masks[i]] = LABEL[GROUP_OF[int(det[i, 5])]]
        return out, found


def group_mask(labels: Any, groups: list[str]) -> Any:
    """The pixels of the label map that belong to the groups."""
    import numpy as np

    return np.isin(labels, [LABEL[g] for g in groups if g in LABEL])


def grown(mask: Any, pixels: int) -> Any:
    """The mask grown by about `pixels` in every direction (the edge of a YOLO mask is coarse,
    and the points of ALIKED like the outline of a person against the background)."""
    import numpy as np
    from PIL import Image, ImageFilter

    if pixels <= 0 or not mask.any():
        return mask
    image = Image.fromarray(mask.astype(np.uint8) * 255)
    return np.asarray(image.filter(ImageFilter.MaxFilter(2 * pixels + 1))) > 127


def fitted(size: tuple[int, int], side: int) -> tuple[int, int]:
    w, h = size
    scale = min(1.0, side / max(w, h))
    return max(1, round(w * scale)), max(1, round(h * scale))


class ObjectsModule:
    id = "objects"
    # Bump when the weights, the preprocessing or the groups change.
    version = "1"

    def __init__(self, options: ModuleOptions) -> None:
        self._options = options
        self._device = resolve_device(options.device)
        self._segmenter: Segmenter | None = None

    def weights_cached(self) -> bool:
        return weights_path().is_file()

    def load(self) -> None:
        import torch

        torch.set_num_threads(self._options.threads)
        self._segmenter = Segmenter(self._device)
        log.info("YOLO26s-seg loaded on %s with %d threads", self._device, self._options.threads)

    def unload(self) -> None:
        self._segmenter = None
        gc.collect()
        if self._device == "cuda":
            import torch

            torch.cuda.empty_cache()

    def run(self, image: bytes) -> Objects:
        from PIL import Image, UnidentifiedImageError

        assert self._segmenter is not None, "load() first"
        try:
            with Image.open(io.BytesIO(image), formats=IMAGE_FORMATS) as opened:
                rgb = opened.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise PermanentError(f"cannot read the image: {exc}") from exc
        labels, found = self._segmenter.labels(rgb, fitted(rgb.size, COVER_SIDE))
        groups: dict[str, dict[str, float]] = {}
        for obj in found:
            group = GROUP_OF.get(obj["class"])
            if group is not None:
                entry = groups.setdefault(group, {"count": 0, "cover": 0.0})
                entry["count"] += 1
        for group, entry in groups.items():
            entry["cover"] = round(float((labels == LABEL[group]).mean()), 4)
        kept = Image.fromarray(labels).resize(fitted(rgb.size, KEEP_SIDE), Image.Resampling.NEAREST)
        png = io.BytesIO()
        kept.save(png, format="PNG", optimize=True)
        return Objects(groups=groups, found=found, labels=png.getvalue())

    def mask_of(self, rgb: Any, size: tuple[int, int], groups: list[str], grow: int) -> Any:
        """The mask of the groups for an image at `size` (the size of its points), grown; None
        when nothing of the groups is in it."""
        if self._segmenter is None:
            self.load()
        assert self._segmenter is not None
        labels, _ = self._segmenter.labels(rgb, size)
        mask = group_mask(labels, groups)
        return grown(mask, grow) if mask.any() else None
