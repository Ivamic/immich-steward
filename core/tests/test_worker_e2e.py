# SPDX-License-Identifier: AGPL-3.0-or-later
"""The real worker against the real core (in process, no network)."""

from typing import Any

import httpx2
from conftest import WORKER_TOKEN, FakeImmich, sync
from fastapi.testclient import TestClient
from sqlalchemy import select

from steward import worker_queue
from steward.models import Asset, ModuleRun
from steward_worker.client import CoreClient
from steward_worker.modules import Candidate
from steward_worker.runner import Worker, WorkerConfig


class EchoModule:
    """Puts a candidate at a fixed point and remembers the image it got."""

    id = "echo"
    version = "1"

    def __init__(self) -> None:
        self.images: list[bytes] = []

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def run(self, image: bytes) -> list[Candidate]:
        self.images.append(image)
        return [Candidate(latitude=45.0, longitude=7.0, score=0.5, radius_m=25_000)]


def test_worker_processes_a_queued_module_run(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    immich_id = fake_immich.add_asset(taken="2024-05-01T10:00:00")
    sync(signed_in)
    app = signed_in.app
    module = EchoModule()

    async def scenario() -> list[Any]:
        async with app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            asset = await db.scalar(select(Asset))
            await worker_queue.enqueue_module(db, asset, "echo")

        # Inside the app's event loop, so that the worker shares its database connections.
        transport = httpx2.ASGITransport(app=app)  # type: ignore[arg-type]
        async with CoreClient("http://core", WORKER_TOKEN, transport=transport) as client:
            worker = Worker(client, {"echo": module}, WorkerConfig(name="e2e"))
            assert await worker.run_once() is True
            assert await worker.run_once() is False

        async with app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            run = await db.scalar(select(ModuleRun))
            return [run.status, run.module_version, run.candidates]

    status, version, candidates = signed_in.portal.call(scenario)  # type: ignore[union-attr]
    assert (status, version) == ("done", "1")
    assert candidates[0]["latitude"] == 45.0
    # The worker got the photo through the core, never talking to Immich itself.
    assert module.images == [f"image:{immich_id}:preview".encode()]
