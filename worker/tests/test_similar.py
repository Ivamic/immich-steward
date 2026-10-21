# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import base64
import struct

from test_runner import FakeCore, StubModule, make_worker

from steward_worker.modules import AVAILABLE, Embedding, ModuleOptions
from steward_worker.modules.similar import DIM, pack


def test_module_is_registered_without_importing_torch() -> None:
    module = AVAILABLE["similar"](ModuleOptions(threads=1, device="cpu"))
    assert (module.id, module.version) == ("similar", "1")


def test_vector_is_packed_as_little_endian_float16() -> None:
    embedding = pack([1.0, -0.5, 0.25])
    assert embedding.dim == 3
    assert struct.unpack("<3e", embedding.data) == (1.0, -0.5, 0.25)


class VectorModule(StubModule):
    def run(self, image: bytes) -> Embedding:  # type: ignore[override]
        self.images.append(image)
        return pack([0.5] * DIM)


def test_vector_is_sent_instead_of_candidates() -> None:
    core, module = FakeCore(), VectorModule()
    job_id = core.add_job()
    worker, _ = make_worker(core, module)

    assert asyncio.run(worker.run_once()) is True
    result = core.results[job_id]
    assert result["candidates"] == []
    assert result["embedding"]["dim"] == DIM
    data = base64.b64decode(result["embedding"]["data"])
    assert struct.unpack(f"<{DIM}e", data)[:2] == (0.5, 0.5)
