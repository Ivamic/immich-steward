# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from conftest import WORKER_TOKEN, FakeImmich, run_jobs, sync
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from steward import worker_queue
from steward.api.worker import PROTOCOL_VERSION
from steward.models import Asset, Job, ModuleRun, Worker

AUTH = {"Authorization": f"Bearer {WORKER_TOKEN}"}


def db_call(client: TestClient, work: Any) -> Any:
    async def go() -> Any:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return await work(db)

    return client.portal.call(go)  # type: ignore[union-attr]


def enqueue(client: TestClient, module: str = "test", priority: int = 0, index: int = 0) -> UUID:
    async def work(db: Any) -> UUID:
        assets = (await db.scalars(select(Asset).order_by(Asset.local_taken_at))).all()
        run = await worker_queue.enqueue_module(db, assets[index], module, priority)
        return UUID(str(run.id))

    result: UUID = db_call(client, work)
    return result


def run_status(client: TestClient, run_id: UUID) -> ModuleRun:
    async def work(db: Any) -> ModuleRun:
        return await db.get(ModuleRun, run_id)

    result: ModuleRun = db_call(client, work)
    return result


def register(
    client: TestClient, name: str = "w1", modules: list[str] | None = None
) -> dict[str, Any]:
    body = {
        "name": name,
        "modules": modules or ["test"],
        "device": "cpu",
        "version": "0.1.0",
        "protocol_version": PROTOCOL_VERSION,
    }
    response = client.post("/api/worker/register", json=body, headers=AUTH)
    assert response.status_code == 200
    worker = AUTH | {"X-Worker-Id": response.json()["worker_id"]}
    return worker


def lease(client: TestClient, worker: dict[str, Any], modules: list[str] | None = None) -> Any:
    return client.post("/api/worker/lease", json={"modules": modules or ["test"]}, headers=worker)


@pytest.fixture
def photos(signed_in: TestClient, fake_immich: FakeImmich) -> TestClient:
    fake_immich.add_asset(taken="2024-05-01T10:00:00")
    fake_immich.add_asset(taken="2024-05-01T11:00:00")
    sync(signed_in)
    return signed_in


def test_token_is_required(client: TestClient) -> None:
    body = {"name": "w", "modules": [], "version": "1", "protocol_version": PROTOCOL_VERSION}
    assert client.post("/api/worker/register", json=body).json()["code"] == "worker_unauthorized"
    wrong = {"Authorization": "Bearer nope"}
    assert client.post("/api/worker/register", json=body, headers=wrong).status_code == 401
    unknown = AUTH | {"X-Worker-Id": "00000000-0000-4000-8000-000000000000"}
    assert lease(client, unknown).json()["code"] == "worker_unknown"
    old = body | {"protocol_version": 0}
    assert client.post("/api/worker/register", json=old, headers=AUTH).status_code == 400


def test_full_cycle(photos: TestClient, fake_immich: FakeImmich) -> None:
    run_id = enqueue(photos)
    worker = register(photos)
    job = lease(photos, worker).json()
    assert job["module"] == "test"
    assert job["attempt"] == 1
    assert run_status(photos, run_id).status == "running"

    image = photos.get(f"/api/worker/jobs/{job['job_id']}/image", headers=worker)
    assert image.status_code == 200
    assert image.content.endswith(b":preview")
    assert (
        photos.post(f"/api/worker/jobs/{job['job_id']}/heartbeat", headers=worker).status_code
        == 204
    )

    result = {
        "module_version": "7",
        "candidates": [{"latitude": 42.4, "longitude": 18.7, "score": 0.8, "radius_m": 5000}],
    }
    done = photos.post(f"/api/worker/jobs/{job['job_id']}/result", json=result, headers=worker)
    assert done.status_code == 204
    run = run_status(photos, run_id)
    assert (run.status, run.module_version) == ("done", "7")
    assert run.candidates[0]["latitude"] == 42.4
    assert run.candidates[0]["kind"] == "point"
    # The job is gone from the queue.
    assert lease(photos, worker).status_code == 204


def test_priority_and_module_filter(photos: TestClient) -> None:
    background = enqueue(photos, index=0)
    urgent = enqueue(photos, index=1, priority=worker_queue.PRIORITY_USER)
    other_module = enqueue(photos, module="geoclip", index=0)
    worker = register(photos)

    first = lease(photos, worker).json()
    second = lease(photos, worker).json()
    assert lease(photos, worker).status_code == 204  # geoclip is not this worker's module
    assert run_status(photos, urgent).job_id == UUID(first["job_id"])
    assert run_status(photos, background).job_id == UUID(second["job_id"])
    assert run_status(photos, other_module).status == "queued"


def test_enqueue_again_reuses_the_active_run_and_raises_priority(photos: TestClient) -> None:
    first = enqueue(photos)
    again = enqueue(photos, priority=worker_queue.PRIORITY_USER)
    assert again == first

    job_id = run_status(photos, first).job_id

    async def priority(db: Any) -> int:
        job = await db.get(Job, job_id)
        return int(job.priority)

    assert db_call(photos, priority) == worker_queue.PRIORITY_USER


def test_two_workers_never_get_the_same_job(photos: TestClient) -> None:
    enqueue(photos, index=0)
    enqueue(photos, index=1)
    a, b = register(photos, "a"), register(photos, "b")
    jobs = {lease(photos, a).json()["job_id"], lease(photos, b).json()["job_id"]}
    assert len(jobs) == 2
    # The holder of a job is checked on every call.
    job_of_a = lease_job_of(photos, a)
    assert photos.post(f"/api/worker/jobs/{job_of_a}/heartbeat", headers=b).json()["code"] == (
        "lease_lost"
    )


def lease_job_of(client: TestClient, worker: dict[str, Any]) -> str:
    async def work(db: Any) -> str:
        job = await db.scalar(select(Job).where(Job.worker_id == UUID(worker["X-Worker-Id"])))
        return str(job.id)

    result: str = db_call(client, work)
    return result


def test_expired_lease_goes_to_another_worker(photos: TestClient) -> None:
    run_id = enqueue(photos)
    a, b = register(photos, "a"), register(photos, "b")
    job_id = lease(photos, a).json()["job_id"]

    async def expire(db: Any) -> None:
        past = datetime.now(UTC) - timedelta(seconds=1)
        await db.execute(update(Job).values(lease_until=past))
        await db.commit()

    db_call(photos, expire)
    taken = lease(photos, b).json()
    assert taken["job_id"] == job_id
    assert taken["attempt"] == 2
    # The first worker comes back too late: its result is refused.
    late = photos.post(
        f"/api/worker/jobs/{job_id}/result",
        json={"module_version": "1", "candidates": []},
        headers=a,
    )
    assert late.json()["code"] == "lease_lost"
    assert run_status(photos, run_id).status == "running"


def test_failures_are_retried_then_given_up(photos: TestClient) -> None:
    run_id = enqueue(photos)
    worker = register(photos)
    for attempt in (1, 2, 3):
        job = lease(photos, worker).json()
        assert job["attempt"] == attempt
        photos.post(
            f"/api/worker/jobs/{job['job_id']}/fail", json={"error": "boom"}, headers=worker
        )
    assert lease(photos, worker).status_code == 204
    run = run_status(photos, run_id)
    assert (run.status, run.error, run.error_code) == ("failed", "boom", "module_error")


def test_hopeless_failure_is_not_retried(photos: TestClient) -> None:
    run_id = enqueue(photos)
    worker = register(photos)
    job = lease(photos, worker).json()
    body = {"error": "cannot decode", "retry": False}
    photos.post(f"/api/worker/jobs/{job['job_id']}/fail", json=body, headers=worker)
    assert run_status(photos, run_id).status == "failed"


def test_lease_expiring_on_the_last_attempt_fails_the_job(photos: TestClient) -> None:
    run_id = enqueue(photos)
    worker = register(photos)

    async def exhaust(db: Any) -> None:
        past = datetime.now(UTC) - timedelta(seconds=1)
        await db.execute(update(Job).values(status="running", attempts=3, lease_until=past))
        await db.commit()

    db_call(photos, exhaust)
    assert lease(photos, worker).status_code == 204
    run = run_status(photos, run_id)
    assert (run.error, run.error_code) == ("lease_expired", "lease_expired")


def test_core_runner_leaves_worker_jobs_alone(photos: TestClient) -> None:
    run_id = enqueue(photos)
    run_jobs(photos)
    assert run_status(photos, run_id).status == "queued"


def test_invalid_results_are_rejected(photos: TestClient) -> None:
    enqueue(photos)
    worker = register(photos)
    job = lease(photos, worker).json()
    bad = {"module_version": "1", "candidates": [{"latitude": 91, "longitude": 0, "score": 0.5}]}
    response = photos.post(f"/api/worker/jobs/{job['job_id']}/result", json=bad, headers=worker)
    assert response.status_code == 422


def immich_id(client: TestClient, run_id: UUID) -> str:
    async def work(db: Any) -> str:
        run = await db.get(ModuleRun, run_id)
        asset = await db.get(Asset, run.asset_id)
        return str(asset.immich_id)

    result: str = db_call(client, work)
    return result


def get_image(client: TestClient, worker: dict[str, Any], job: dict[str, Any]) -> Any:
    return client.get(f"/api/worker/jobs/{job['job_id']}/image", headers=worker)


@pytest.mark.parametrize("status", [400, 404])
def test_photo_immich_cannot_give_fails_at_once(
    photos: TestClient, fake_immich: FakeImmich, status: int
) -> None:
    run_id = enqueue(photos)
    fake_immich.thumbnail_status[immich_id(photos, run_id)] = status
    worker = register(photos)
    response = get_image(photos, worker, lease(photos, worker).json())
    assert response.status_code == 410
    assert response.json()["code"] == "image_unavailable"
    run = run_status(photos, run_id)
    assert (run.status, run.error_code) == ("failed", "image_unavailable")
    assert f"HTTP {status}" in (run.error or "")
    assert lease(photos, worker).status_code == 204


def test_immich_server_error_is_retried_then_recorded(
    photos: TestClient, fake_immich: FakeImmich
) -> None:
    run_id = enqueue(photos)
    fake_immich.thumbnail_status[immich_id(photos, run_id)] = 500
    worker = register(photos)
    for attempt in (1, 2, 3):
        job = lease(photos, worker).json()
        assert job["attempt"] == attempt
        assert get_image(photos, worker, job).status_code == 410
    run = run_status(photos, run_id)
    assert (run.status, run.error_code) == ("failed", "image_unavailable")


def test_rejected_api_key_is_recorded(photos: TestClient, fake_immich: FakeImmich) -> None:
    run_id = enqueue(photos)
    fake_immich.thumbnail_status[immich_id(photos, run_id)] = 401
    worker = register(photos)
    assert get_image(photos, worker, lease(photos, worker).json()).status_code == 410
    assert run_status(photos, run_id).error_code == "immich_auth"


def test_unreachable_immich_does_not_use_up_attempts(
    photos: TestClient, fake_immich: FakeImmich
) -> None:
    run_id = enqueue(photos)
    fake_immich.thumbnails_unreachable = True
    worker = register(photos)
    for _ in range(5):
        response = get_image(photos, worker, lease(photos, worker).json())
        assert response.status_code == 503
        assert response.json()["code"] == "immich_unreachable"
    assert run_status(photos, run_id).status == "queued"

    fake_immich.thumbnails_unreachable = False
    job = lease(photos, worker).json()
    assert job["attempt"] == 1
    assert get_image(photos, worker, job).status_code == 200


def test_failure_codes_from_the_worker(photos: TestClient) -> None:
    first, second = enqueue(photos, index=0), enqueue(photos, index=1)
    worker = register(photos)
    job = lease(photos, worker).json()
    body = {"error": "bad result", "retry": False, "code": "worker_error"}
    photos.post(f"/api/worker/jobs/{job['job_id']}/fail", json=body, headers=worker)
    assert run_status(photos, first).error_code == "worker_error"
    # A worker before 0.3 sends no code: it follows from `retry`.
    job = lease(photos, worker).json()
    body = {"error": "cannot decode", "retry": False}
    photos.post(f"/api/worker/jobs/{job['job_id']}/fail", json=body, headers=worker)
    assert run_status(photos, second).error_code == "image_invalid"


def register_instance(client: TestClient, name: str, instance: str) -> Any:
    body = {
        "name": name,
        "modules": ["test"],
        "device": "cpu",
        "version": "0.3.0",
        "protocol_version": PROTOCOL_VERSION,
        "instance_id": instance,
    }
    return client.post("/api/worker/register", json=body, headers=AUTH)


def test_two_running_workers_cannot_share_a_name(client: TestClient) -> None:
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    response = register_instance(client, "laptop", first)
    assert response.status_code == 200
    worker = AUTH | {"X-Worker-Id": response.json()["worker_id"]}
    # The same process may register again (e.g. after the core forgot it).
    assert register_instance(client, "laptop", first).status_code == 200

    taken = register_instance(client, "laptop", second)
    assert taken.status_code == 409
    assert taken.json()["code"] == "worker_name_taken"
    # Workers before 0.3 send no instance id and are never refused.
    assert (
        client.post(
            "/api/worker/register",
            json={"name": "laptop", "modules": [], "version": "0.2.2", "protocol_version": 1},
            headers=AUTH,
        ).status_code
        == 200
    )

    register_instance(client, "laptop", first)
    client.post("/api/worker/bye", headers=worker)
    # Once the first one has stopped, the name is free.
    assert register_instance(client, "laptop", second).status_code == 200


def test_name_of_a_silent_worker_can_be_taken(client: TestClient) -> None:
    register_instance(client, "desktop", str(uuid.uuid4()))

    async def silence(db: Any) -> None:
        await db.execute(update(Worker).values(last_seen_at=datetime.now(UTC) - timedelta(hours=1)))
        await db.commit()

    db_call(client, silence)
    assert register_instance(client, "desktop", str(uuid.uuid4())).status_code == 200
