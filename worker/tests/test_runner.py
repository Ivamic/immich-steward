# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx2
import pytest

from steward_worker.client import CoreClient, ImmichUnreachable, NameTaken
from steward_worker.modules import Candidate, PermanentError
from steward_worker.runner import Worker, WorkerConfig

TOKEN = "secret"


@dataclass
class FakeCore:
    """The worker API of the core, in memory."""

    jobs: list[dict[str, Any]] = field(default_factory=list)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: dict[str, dict[str, Any]] = field(default_factory=dict)
    registrations: int = 0
    known_workers: set[str] = field(default_factory=set)
    lose_lease: bool = False
    # Status and body of the answers to /image and /result instead of success.
    image_error: tuple[int, dict[str, Any]] | None = None
    result_error: tuple[int, dict[str, Any]] | None = None
    goodbyes: int = 0
    name_taken: bool = False
    instances: list[str] = field(default_factory=list)

    def add_job(self, module: str = "stub") -> str:
        job_id = str(uuid.uuid4())
        self.jobs.append({"job_id": job_id, "module": module, "asset_id": str(uuid.uuid4())})
        return job_id

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx2.Response(401, json={"code": "worker_unauthorized"})
        path = request.url.path.removeprefix("/api/worker")
        if path == "/bye":
            self.goodbyes += 1
            return httpx2.Response(204)
        if path == "/register":
            if self.name_taken:
                return httpx2.Response(409, json={"code": "worker_name_taken"})
            self.registrations += 1
            self.instances.append(json.loads(request.content)["instance_id"])
            worker_id = str(uuid.uuid4())
            self.known_workers.add(worker_id)
            return httpx2.Response(200, json={"worker_id": worker_id, "lease_seconds": 30})
        if request.headers.get("x-worker-id") not in self.known_workers:
            return httpx2.Response(401, json={"code": "worker_unknown"})
        if path == "/lease":
            modules = json.loads(request.content)["modules"]
            job = next((j for j in self.jobs if j["module"] in modules), None)
            if job is None:
                return httpx2.Response(204)
            self.jobs.remove(job)
            return httpx2.Response(200, json=job | {"attempt": 1, "lease_seconds": 30})
        job_id = path.split("/")[2]
        if path.endswith("/image"):
            if self.image_error:
                return httpx2.Response(self.image_error[0], json=self.image_error[1])
            return httpx2.Response(200, content=b"image-bytes")
        if self.lose_lease:
            return httpx2.Response(409, json={"code": "lease_lost"})
        if path.endswith("/result"):
            if self.result_error:
                return httpx2.Response(self.result_error[0], json=self.result_error[1])
            self.results[job_id] = json.loads(request.content)
        elif path.endswith("/fail"):
            self.failures[job_id] = json.loads(request.content)
        return httpx2.Response(204)


class StubModule:
    id = "stub"
    version = "3"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.loads = self.unloads = 0
        self.images: list[bytes] = []

    def load(self) -> None:
        self.loads += 1

    def unload(self) -> None:
        self.unloads += 1

    def run(self, image: bytes) -> list[Candidate]:
        self.images.append(image)
        if self.error:
            raise self.error
        return [Candidate(latitude=42.4, longitude=18.7, score=0.9, radius_m=1000)]


def make_worker(
    core: FakeCore,
    module: StubModule,
    busy: bool = False,
    unload_after_s: float = 600,
    real_sleep: bool = False,
) -> tuple[Worker, CoreClient]:
    client = CoreClient("http://core.test", TOKEN, transport=httpx2.MockTransport(core.handler))
    config = WorkerConfig(name="test", unload_after_s=unload_after_s)

    async def no_sleep(_: float) -> None:
        pass

    worker = Worker(
        client,
        {"stub": module},
        config,
        sleep=None if real_sleep else no_sleep,
        busy=lambda _: busy,
    )
    return worker, client


def test_runs_a_job_and_reports_the_result() -> None:
    core, module = FakeCore(), StubModule()
    job_id = core.add_job()
    worker, _ = make_worker(core, module)

    assert asyncio.run(worker.run_once()) is True
    assert module.images == [b"image-bytes"]
    assert module.loads == 1
    result = core.results[job_id]
    assert result["module_version"] == "3"
    assert result["candidates"][0] == {
        "latitude": 42.4,
        "longitude": 18.7,
        "score": 0.9,
        "radius_m": 1000,
        "kind": "point",
        "evidence": {},
    }
    assert asyncio.run(worker.run_once()) is False  # queue is empty


def test_module_errors_are_reported_for_retry() -> None:
    core = FakeCore()
    retry_job = core.add_job()
    worker, _ = make_worker(core, StubModule(RuntimeError("out of memory")))
    asyncio.run(worker.run_once())
    assert core.failures[retry_job] == {
        "error": "RuntimeError: out of memory",
        "retry": True,
        "code": "module_error",
    }

    hopeless = FakeCore()
    job = hopeless.add_job()
    worker, _ = make_worker(hopeless, StubModule(PermanentError("not an image")))
    asyncio.run(worker.run_once())
    assert hopeless.failures[job]["retry"] is False
    assert hopeless.failures[job]["code"] == "image_invalid"


def test_photo_the_core_cannot_give_is_dropped() -> None:
    body = {"code": "image_unavailable", "params": {"reason": "image_unavailable"}}
    core = FakeCore(image_error=(410, body))
    core.add_job()
    module = StubModule()
    worker, _ = make_worker(core, module)
    assert asyncio.run(worker.run_once()) is True
    # The core has recorded the failure itself; the module never ran.
    assert (core.results, core.failures, module.loads) == ({}, {}, 0)


def test_unreachable_immich_makes_the_worker_wait() -> None:
    core = FakeCore(image_error=(503, {"code": "immich_unreachable", "params": {}}))
    core.add_job()
    worker, _ = make_worker(core, StubModule())
    with pytest.raises(ImmichUnreachable):
        asyncio.run(worker.run_once())
    assert core.failures == {}


def test_refused_result_is_reported_as_a_failure() -> None:
    core = FakeCore(result_error=(422, {"code": "validation_error", "params": {}}))
    job_id = core.add_job()
    worker, _ = make_worker(core, StubModule())
    assert asyncio.run(worker.run_once()) is True
    failure = core.failures[job_id]
    assert (failure["retry"], failure["code"]) == (True, "worker_error")
    assert "HTTP 422" in failure["error"]


def test_lost_lease_drops_the_job_quietly() -> None:
    core = FakeCore(lose_lease=True)
    core.add_job()
    worker, _ = make_worker(core, StubModule())
    assert asyncio.run(worker.run_once()) is True
    assert core.results == {}


def test_registers_again_when_the_core_forgets_the_worker() -> None:
    core = FakeCore()
    worker, _ = make_worker(core, StubModule())
    asyncio.run(worker.run_once())
    core.known_workers.clear()  # the core database was reset
    job_id = core.add_job()

    async def twice() -> None:
        await worker.run_once()  # gets worker_unknown
        await worker.run_once()  # registers again and works

    asyncio.run(twice())
    assert core.registrations == 2
    assert job_id in core.results


def test_waits_while_the_system_is_busy() -> None:
    core = FakeCore()
    core.add_job()
    worker, _ = make_worker(core, StubModule(), busy=True)
    assert asyncio.run(worker.run_once()) is False
    assert core.jobs  # nothing was leased


def test_idle_modules_are_unloaded() -> None:
    core, module = FakeCore(), StubModule()
    core.add_job()
    # Below zero: on Windows the monotonic clock may not move between two calls.
    worker, _ = make_worker(core, module, unload_after_s=-1)

    async def scenario() -> None:
        await worker.run_once()
        worker._unload_idle()
        core.add_job()
        await worker.run_once()

    asyncio.run(scenario())
    assert (module.loads, module.unloads) == (2, 1)


def test_run_forever_stops_cleanly() -> None:
    core, module = FakeCore(), StubModule()
    # The real sleep: waiting must be interruptible by stop().
    worker, _ = make_worker(core, module, real_sleep=True)

    async def scenario() -> None:
        task = asyncio.create_task(worker.run_forever())
        await asyncio.sleep(0.05)
        worker.stop()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())
    assert core.goodbyes == 1  # the core stops counting it as available


@pytest.mark.parametrize("value", [None, 1e9])
def test_system_busy_without_limit_or_with_a_high_one(value: float | None) -> None:
    from steward_worker.load import system_busy

    assert system_busy(value) is False


def test_the_same_process_keeps_its_instance_id() -> None:
    core = FakeCore()
    worker, _ = make_worker(core, StubModule())
    asyncio.run(worker.run_once())
    core.known_workers.clear()
    asyncio.run(worker.run_once())  # registers again
    asyncio.run(worker.run_once())
    assert len(core.instances) == 2
    assert core.instances[0] == core.instances[1]


def test_taken_name_is_reported() -> None:
    worker, _ = make_worker(FakeCore(name_taken=True), StubModule())
    with pytest.raises(NameTaken):
        asyncio.run(worker.run_once())


def test_one_model_at_a_time() -> None:
    core = FakeCore()
    first, second = StubModule(), StubModule()
    second.id = "other"
    core.add_job("stub")
    core.add_job("other")
    core.add_job("other")
    client = CoreClient("http://core.test", TOKEN, transport=httpx2.MockTransport(core.handler))

    async def no_sleep(_: float) -> None:
        pass

    config = WorkerConfig(name="test", one_model=True)
    worker = Worker(
        client, {"stub": first, "other": second}, config, sleep=no_sleep, busy=lambda _: False
    )
    for _ in range(3):
        asyncio.run(worker.run_once())
    # The first model is freed before the second one is loaded, and only once.
    assert (first.loads, first.unloads) == (1, 1)
    assert (second.loads, second.unloads) == (1, 0)
