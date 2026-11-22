# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio

import pytest
from test_runner import FakeCore, StubModule, make_worker

from steward_worker.modules import AVAILABLE, ModuleOptions, Orientation
from steward_worker.modules.orientation import combine


def test_module_is_registered_without_importing_torch() -> None:
    module = AVAILABLE["orientation"](ModuleOptions(threads=1, device="cpu"))
    assert (module.id, module.version) == ("orientation", "1")


def test_four_looks_add_up_by_the_turn_of_the_photo() -> None:
    # A photo turned once (90 degrees counter-clockwise): turned once more it looks turned
    # twice, and so on; each look agrees with "turned once".
    looks = [
        [0.0, 0.9, 0.1, 0.0],
        [0.0, 0.0, 0.8, 0.2],
        [0.1, 0.0, 0.0, 0.9],
        [0.7, 0.1, 0.0, 0.2],
    ]
    probs = combine(looks)
    assert max(range(4), key=lambda c: probs[c]) == 1
    assert probs[1] == pytest.approx((0.9 + 0.8 + 0.9 + 0.7) / 4)
    assert sum(probs) == pytest.approx(1.0)


class TurnedModule(StubModule):
    def run(self, image: bytes) -> Orientation:  # type: ignore[override]
        self.images.append(image)
        return Orientation(probs=(0.02, 0.92, 0.03, 0.03), looks=4)


def test_the_answer_is_sent_instead_of_candidates() -> None:
    core, module = FakeCore(), TurnedModule()
    job_id = core.add_job()
    worker, _ = make_worker(core, module)

    assert asyncio.run(worker.run_once()) is True
    result = core.results[job_id]
    assert result["candidates"] == []
    assert result["orientation"] == {"probs": [0.02, 0.92, 0.03, 0.03], "looks": 4}
