# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "torch==2.14.1",
#     "torchvision==0.29.1",
#     "ultralytics>=8.4.0",
# ]
#
# [tool.uv.sources]
# torch = { index = "pytorch-cpu" }
# torchvision = { index = "pytorch-cpu" }
#
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
# ///
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Makes the weights of the worker's module `objects` (D-248): YOLO26s-seg of Ultralytics
(AGPL-3.0, the code and the weights) exported to TorchScript with NMS inside, so that the worker
runs it with plain PyTorch and torchvision, without the package `ultralytics`.

The file is published as a file of the release "models-1" of the app; its address and SHA-256 are
in `steward_worker/modules/objects.py`. Run only to make it again (another size, a newer YOLO):

    uv run worker/tools/export_yolo26_seg.py [--size s] [--out folder]

then publish the file and change the address and the SHA-256 (and the module's version). The
PyTorch here is the one of the worker's lock file: a TorchScript file made with a newer PyTorch may
not load in an older one.
"""

import argparse
import hashlib
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--size", default="s", choices=["n", "s", "m", "l", "x"])
    parser.add_argument("--out", default=".", help="folder for the .pt and the .torchscript")
    args = parser.parse_args()

    import torch
    from ultralytics import YOLO

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.chdir(out)  # Ultralytics downloads the weights into the current folder
    model = YOLO(f"yolo26{args.size}-seg.pt")
    path = Path(model.export(format="torchscript", imgsz=640, nms=True, device="cpu"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"{path} ({path.stat().st_size / 2**20:.1f} MB), torch {torch.__version__}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
