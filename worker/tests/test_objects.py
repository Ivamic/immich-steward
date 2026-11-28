# SPDX-License-Identifier: AGPL-3.0-or-later
"""People, animals and vehicles (D-248): the module `objects` and the masks of `details`."""

import asyncio
import base64
import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from test_runner import FakeCore, StubModule, make_worker

from steward_worker.modules import AVAILABLE, ModuleOptions, Objects, PairMatch


def test_module_is_registered_without_importing_torch() -> None:
    module = AVAILABLE["objects"](ModuleOptions(threads=1, device="cpu"))
    assert (module.id, module.version) == ("objects", "1")


class FoundModule(StubModule):
    def run(self, image: bytes) -> Objects:  # type: ignore[override]
        self.images.append(image)
        return Objects(
            groups={"person": {"count": 2, "cover": 0.31}},
            found=[{"class": 0, "confidence": 0.9, "box": [0.1, 0.2, 0.4, 0.9]}],
            labels=b"png",
        )


def test_the_answer_is_sent_instead_of_candidates() -> None:
    core, module = FakeCore(), FoundModule()
    job_id = core.add_job()
    worker, _ = make_worker(core, module)

    assert asyncio.run(worker.run_once()) is True
    result = core.results[job_id]
    assert result["candidates"] == []
    assert result["objects"] == {
        "groups": {"person": {"count": 2, "cover": 0.31}},
        "found": [{"class": 0, "confidence": 0.9, "box": [0.1, 0.2, 0.4, 0.9]}],
        "labels": base64.b64encode(b"png").decode("ascii"),
    }


class MaskingModule(StubModule):
    """Compares as `details` does, and keeps what it was asked to leave out."""

    def __init__(self) -> None:
        super().__init__()
        self.masks: list[dict[str, Any] | None] = []

    def compare(
        self, image: bytes, others: Sequence[bytes], masks: dict[str, Any] | None = None
    ) -> list[PairMatch | None]:
        self.masks.append(masks)
        return [PairMatch(matches=10, inliers=5, masked=bool(masks)) for _ in others]


def test_the_masks_of_the_job_reach_the_module_and_come_back() -> None:
    core, module = FakeCore(), MaskingModule()
    job_id = core.add_job(others=["a"])
    core.jobs[-1]["masks"] = {"groups": ["person", "animal"], "grow": 6}
    worker, _ = make_worker(core, module)

    assert asyncio.run(worker.run_once()) is True
    assert module.masks == [{"groups": ["person", "animal"], "grow": 6}]
    assert core.results[job_id]["pairs"][0]["masked"] is True


def test_a_job_without_masks_compares_as_before() -> None:
    core, module = FakeCore(), MaskingModule()
    job_id = core.add_job(others=["a"])
    worker, _ = make_worker(core, module)

    assert asyncio.run(worker.run_once()) is True
    assert module.masks == [None]
    assert core.results[job_id]["pairs"][0]["masked"] is False


# --- With PyTorch (not in CI): the export's output read back, points left out ---------------------


def fake_export(path: Path, det: list[list[float]]) -> None:
    """A TorchScript file shaped like the export of YOLO26-seg with NMS: (1, 300, 38) detections
    (box in the 640 letterboxed pixels, confidence, class, 32 coefficients) and (1, 32, 160, 160)
    prototypes. The prototypes are all 1 and the coefficients all 1: every mask is its box."""
    torch = pytest.importorskip("torch")
    pytest.importorskip("torchvision")
    rows = torch.zeros(1, 300, 38)
    for i, row in enumerate(det):
        rows[0, i, :6] = torch.tensor(row)
        rows[0, i, 6:] = 1.0

    class Fake(torch.nn.Module):  # type: ignore[misc,name-defined]  # torch is not in CI
        def __init__(self) -> None:
            super().__init__()
            self.register_buffer("det", rows)
            self.register_buffer("protos", torch.ones(1, 32, 160, 160))

        def forward(self, x: Any) -> tuple[Any, Any]:
            return self.det, self.protos

    torch.jit.save(torch.jit.script(Fake()), str(path))


def picture(width: int = 640, height: int = 480) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (width, height), (90, 140, 200)).save(out, format="JPEG")
    return out.getvalue()


def test_the_groups_their_share_and_the_label_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A 640 x 480 photo is letterboxed with 80 px above and below. A person in the left half,
    # a dog in the bottom right quarter, a chair (not a group, only listed).
    fake_export(
        tmp_path / "fake.torchscript",
        [
            [0, 80, 320, 560, 0.9, 0],
            [320, 320, 640, 560, 0.8, 16],
            [400, 100, 500, 200, 0.7, 56],
            [0, 80, 640, 560, 0.1, 2],  # below the confidence threshold
        ],
    )
    monkeypatch.setenv("STEWARD_OBJECTS_WEIGHTS", str(tmp_path / "fake.torchscript"))
    from PIL import Image

    from steward_worker.modules.objects import KEEP_SIDE, LABEL, ObjectsModule

    module = ObjectsModule(ModuleOptions(threads=1, device="cpu"))
    module.load()
    found = module.run(picture())
    assert set(found.groups) == {"person", "animal"}
    assert found.groups["person"]["count"] == 1
    assert found.groups["person"]["cover"] == pytest.approx(0.5, abs=0.02)
    assert found.groups["animal"]["cover"] == pytest.approx(0.25, abs=0.02)
    assert sorted(f["class"] for f in found.found) == [0, 16, 56]
    person = next(f for f in found.found if f["class"] == 0)
    assert person["box"] == pytest.approx([0.0, 0.0, 0.5, 1.0], abs=0.01)
    labels = Image.open(io.BytesIO(found.labels))
    assert max(labels.size) == KEEP_SIDE
    assert labels.getpixel((5, 5)) == LABEL["person"]
    assert labels.getpixel((labels.width - 5, labels.height - 5)) == LABEL["animal"]


def test_points_in_the_mask_are_left_out() -> None:
    torch = pytest.importorskip("torch")
    import numpy as np

    from steward_worker.modules.details import keep_points
    from steward_worker.modules.objects import grown

    features = {
        "keypoints": torch.tensor([[[1.0, 1.0], [8.0, 1.0], [1.0, 8.0]]]),
        "descriptors": torch.arange(6.0).view(1, 3, 2),
        "image_size": torch.tensor([[10, 10]]),
    }
    mask = np.zeros((10, 10), dtype=bool)
    mask[0:3, 0:3] = True
    kept = keep_points(features, mask)
    assert kept["keypoints"].tolist() == [[[8.0, 1.0], [1.0, 8.0]]]
    assert kept["descriptors"].tolist() == [[[2.0, 3.0], [4.0, 5.0]]]
    assert kept["image_size"] is features["image_size"]
    # Grown by 6 pixels the mask reaches the other two points as well.
    assert keep_points(features, grown(mask, 6))["keypoints"].shape[1] == 0
