# SPDX-License-Identifier: AGPL-3.0-or-later
"""Processing the photos of the locked folder: only while it is open (D-216)."""

from typing import Any

from conftest import FakeImmich, run_jobs
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_locked_open import close_idle, connected, idle_for, open_with
from test_worker_api import db_call, lease, register

from steward import worker_queue
from steward.models import Asset


def enqueue_locked(client: TestClient) -> None:
    async def work(db: Any) -> None:
        asset = await db.scalar(select(Asset).where(Asset.visibility == "locked"))
        await worker_queue.enqueue_module(db, asset, "test", 0)

    db_call(client, work)


def locked_photo(client: TestClient, fake: FakeImmich) -> TestClient:
    fake.add_asset(visibility="locked")
    connected(client, fake)
    open_with(client, "123456")
    run_jobs(client)
    return client


def test_jobs_of_locked_photos_wait_for_the_pin(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    client = locked_photo(signed_in, fake_immich)
    client.post("/api/locked/close")
    enqueue_locked(client)
    worker = register(client)
    assert lease(client, worker).status_code == 204
    assert client.get("/api/library/workers").json()["locked_waiting"] == 1

    open_with(client, "123456")
    response = lease(client, worker)
    assert response.status_code == 200
    assert client.get("/api/library/workers").json()["locked_waiting"] == 0
    # The worker gets the photo through the session of the open folder.
    image = client.get(f"/api/worker/jobs/{response.json()['job_id']}/image", headers=worker)
    assert image.status_code == 200


def test_a_folder_closed_after_the_lease_gives_the_job_back(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    client = locked_photo(signed_in, fake_immich)
    enqueue_locked(client)
    worker = register(client)
    job = lease(client, worker).json()
    client.post("/api/locked/close")
    image = client.get(f"/api/worker/jobs/{job['job_id']}/image", headers=worker)
    assert image.status_code == 503
    assert image.json()["code"] == "locked_closed"
    assert client.get("/api/library/workers").json()["locked_waiting"] == 1


def test_the_folder_stays_open_while_its_photos_are_processed(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    client = locked_photo(signed_in, fake_immich)
    enqueue_locked(client)
    idle_for(client, 30)
    close_idle(client)
    assert client.get("/api/locked").json()["open"] is True
    # But not more than an hour without a user action.
    idle_for(client, 61)
    close_idle(client)
    assert client.get("/api/locked").json()["open"] is False


def test_locked_photos_are_queued_automatically(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    client = locked_photo(signed_in, fake_immich)

    async def work(db: Any) -> int:
        return await worker_queue.auto_enqueue(db, "geoclip")

    assert db_call(client, work) == 1
    # Closed, the job stays in the queue, but is not handed out.
    client.post("/api/locked/close")
    worker = register(client, modules=["geoclip"])
    assert lease(client, worker, ["geoclip"]).status_code == 204
