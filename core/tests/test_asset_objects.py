# SPDX-License-Identifier: AGPL-3.0-or-later
"""People, animals and vehicles in the photos (D-248): the answers of the `objects` module."""

import base64
import uuid
from typing import Any

import pytest
from conftest import WORKER_TOKEN, FakeImmich, sync
from fastapi.testclient import TestClient
from sqlalchemy import select

from steward import worker_queue
from steward.api.worker import PROTOCOL_VERSION
from steward.models import AssetObjects

AUTH = {"Authorization": f"Bearer {WORKER_TOKEN}"}
GPS = {"latitude": 42.4, "longitude": 19.26}
PERSON = {"person": {"count": 2, "cover": 0.31}}
FOUND = [{"class": 0, "confidence": 0.9, "box": [0.1, 0.2, 0.4, 0.9]}]
LABELS = base64.b64encode(b"\x89PNG-label-map").decode("ascii")


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    """File name -> local id."""
    fake_immich.add_asset(taken="2024-05-01T10:00:00", originalFileName="todo.jpg")
    fake_immich.add_asset(taken="2024-05-01T11:00:00", originalFileName="gps.jpg", exif=GPS)
    fake_immich.add_asset(
        taken="2024-05-01T12:00:00", originalFileName="old.jpg", visibility="archive"
    )
    fake_immich.add_asset(taken="2024-05-01T13:00:00", originalFileName="clip.mp4", type="VIDEO")
    sync(signed_in)
    params: dict[str, Any] = {"month": "2024-05", "archived": True, "show": ["todo", "with"]}
    items = signed_in.get("/api/assets", params=params).json()
    return {item["file_name"]: item["id"] for item in items}


def db_call(client: TestClient, work: Any) -> Any:
    async def go() -> Any:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return await work(db)

    return client.portal.call(go)  # type: ignore[union-attr]


def start_worker(client: TestClient) -> dict[str, str]:
    body = {
        "name": "laptop",
        "modules": ["objects"],
        "device": "cuda",
        "version": "0.15.0",
        "protocol_version": PROTOCOL_VERSION,
    }
    worker_id = client.post("/api/worker/register", json=body, headers=AUTH).json()["worker_id"]
    return AUTH | {"X-Worker-Id": worker_id}


def schedule(client: TestClient) -> None:
    runner = client.app.state.job_runner  # type: ignore[attr-defined]
    client.portal.call(runner.schedule_modules)  # type: ignore[union-attr]


def answer_all(client: TestClient, worker: dict[str, str], groups: dict[str, Any]) -> list[str]:
    """Leases every queued job and answers it; the ids of the photos answered."""
    done: list[str] = []
    while True:
        lease = client.post("/api/worker/lease", json={"modules": ["objects"]}, headers=worker)
        if lease.status_code == 204:
            return done
        job = lease.json()
        body = {
            "module_version": "1",
            "candidates": [],
            "objects": {"groups": groups, "found": FOUND, "labels": LABELS},
        }
        result = client.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)
        assert result.status_code == 204
        done.append(job["asset_id"])


def stored(client: TestClient) -> dict[str, AssetObjects]:
    async def work(db: Any) -> dict[str, AssetObjects]:
        return {str(row.asset_id): row for row in await db.scalars(select(AssetObjects))}

    result: dict[str, AssetObjects] = db_call(client, work)
    return result


def test_every_photo_and_video_is_looked_at(library: dict[str, str], signed_in: TestClient) -> None:
    worker = start_worker(signed_in)
    schedule(signed_in)
    # With a location or not, archived, videos too (by the preview).
    assert sorted(answer_all(signed_in, worker, PERSON)) == sorted(library.values())
    rows = stored(signed_in)
    assert set(rows) == set(library.values())
    row = rows[library["clip.mp4"]]
    assert row.groups == PERSON
    assert row.found == FOUND
    assert row.labels == b"\x89PNG-label-map"
    # Looked at once.
    schedule(signed_in)
    assert answer_all(signed_in, worker, PERSON) == []


def test_the_answer_goes_when_the_image_changes(
    library: dict[str, str], signed_in: TestClient
) -> None:
    worker = start_worker(signed_in)
    schedule(signed_in)
    answer_all(signed_in, worker, {})

    async def work(db: Any) -> None:
        await worker_queue.forget_results(db, [uuid.UUID(library["todo.jpg"])])
        await db.commit()

    db_call(signed_in, work)
    assert library["todo.jpg"] not in stored(signed_in)
    schedule(signed_in)
    assert answer_all(signed_in, worker, {}) == [library["todo.jpg"]]


@pytest.mark.parametrize(
    "objects",
    [
        None,
        {"groups": {"ghost": {"count": 1, "cover": 0.1}}, "found": [], "labels": LABELS},
        {"groups": {"person": {"count": 1, "cover": 1.5}}, "found": [], "labels": LABELS},
        {"groups": {}, "found": [], "labels": "not base64!"},
    ],
)
def test_a_wrong_answer_is_refused(
    library: dict[str, str], signed_in: TestClient, objects: dict[str, Any] | None
) -> None:
    worker = start_worker(signed_in)
    schedule(signed_in)
    job = signed_in.post("/api/worker/lease", json={"modules": ["objects"]}, headers=worker).json()
    body: dict[str, Any] = {"module_version": "1", "candidates": []}
    if objects is not None:
        body["objects"] = objects
    result = signed_in.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)
    assert result.status_code == 422
