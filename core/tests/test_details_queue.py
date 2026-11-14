# SPDX-License-Identifier: AGPL-3.0-or-later
"""Jobs of pair modules (`details`): the photo of the job is compared with other photos."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_worker_api import db_call, lease, register

from steward import worker_queue
from steward.models import Asset, DetailMatch, ModuleRun


@pytest.fixture
def photos(signed_in: TestClient, fake_immich: FakeImmich) -> TestClient:
    fake_immich.add_asset(taken="2024-05-01T10:00:00")
    fake_immich.add_asset(taken="2024-05-01T11:00:00")
    sync(signed_in)
    return signed_in


def asset_ids(client: TestClient) -> list[UUID]:
    async def work(db: Any) -> list[UUID]:
        return list(await db.scalars(select(Asset.id).order_by(Asset.local_taken_at)))

    result: list[UUID] = db_call(client, work)
    return result


def enqueue_pairs(client: TestClient, others: list[UUID], index: int = 0) -> UUID:
    async def work(db: Any) -> UUID:
        assets = (await db.scalars(select(Asset).order_by(Asset.local_taken_at))).all()
        run = await worker_queue.enqueue_pairs(db, assets[index], "details", others)
        return UUID(str(run.id))

    result: UUID = db_call(client, work)
    return result


def matches(client: TestClient) -> list[DetailMatch]:
    async def work(db: Any) -> list[DetailMatch]:
        return list(await db.scalars(select(DetailMatch)))

    result: list[DetailMatch] = db_call(client, work)
    return result


def pair(other: UUID, inliers: int = 140) -> dict[str, Any]:
    return {
        "other": str(other),
        "matches": 300,
        "inliers": inliers,
        "lines": [[0.1, 0.2, 0.3, 0.4]],
    }


def test_photo_is_compared_with_the_named_photos(
    photos: TestClient, fake_immich: FakeImmich
) -> None:
    first, second = asset_ids(photos)
    stranger = uuid4()
    run_id = enqueue_pairs(photos, [second, first, second])
    worker = register(photos, modules=["details"])

    job = lease(photos, worker, ["details"]).json()
    # Not with itself, and each photo once.
    assert job["others"] == [str(second)]

    url = f"/api/worker/jobs/{job['job_id']}/image"
    assert photos.get(url, headers=worker).content.endswith(b":preview")
    other = photos.get(url, params={"other": str(second)}, headers=worker)
    assert other.status_code == 200
    assert other.content.endswith(b":preview")
    assert other.content != photos.get(url, headers=worker).content
    # A photo the job did not name is not handed out, whether it exists or not.
    for unnamed in (first, stranger):
        refused = photos.get(url, params={"other": str(unnamed)}, headers=worker)
        assert (refused.status_code, refused.json()["code"]) == (404, "other_unavailable")

    body = {"module_version": "1", "candidates": [], "pairs": [pair(second), pair(stranger)]}
    assert (
        photos.post(
            f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker
        ).status_code
        == 204
    )

    async def run_of(db: Any) -> ModuleRun:
        run: ModuleRun = await db.get(ModuleRun, run_id)
        return run

    assert db_call(photos, run_of).status == "done"
    kept = matches(photos)
    assert [(m.asset_id, m.other_id, m.matches, m.inliers) for m in kept] == [
        (first, second, 300, 140)
    ]
    assert kept[0].lines == [[0.1, 0.2, 0.3, 0.4]]
    assert kept[0].module_version == "1"


def test_a_new_answer_replaces_the_older_one(photos: TestClient) -> None:
    _, second = asset_ids(photos)
    worker = register(photos, modules=["details"])
    for inliers in (40, 150):
        enqueue_pairs(photos, [second])
        job = lease(photos, worker, ["details"]).json()
        body = {"module_version": "1", "candidates": [], "pairs": [pair(second, inliers)]}
        photos.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)

    assert [m.inliers for m in matches(photos)] == [150]


def test_a_photo_immich_cannot_give_is_skipped_not_failed(
    photos: TestClient, fake_immich: FakeImmich
) -> None:
    _, second = asset_ids(photos)
    run_id = enqueue_pairs(photos, [second])
    worker = register(photos, modules=["details"])
    job = lease(photos, worker, ["details"]).json()

    async def immich_id_of(db: Any) -> str:
        asset = await db.get(Asset, second)
        return str(asset.immich_id)

    fake_immich.thumbnail_status[db_call(photos, immich_id_of)] = 404
    url = f"/api/worker/jobs/{job['job_id']}/image"
    refused = photos.get(url, params={"other": str(second)}, headers=worker)
    assert (refused.status_code, refused.json()["code"]) == (404, "other_unavailable")

    # The job goes on: the worker sends what it has.
    body = {"module_version": "1", "candidates": [], "pairs": []}
    assert (
        photos.post(
            f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker
        ).status_code
        == 204
    )

    async def run_of(db: Any) -> ModuleRun:
        run: ModuleRun = await db.get(ModuleRun, run_id)
        return run

    assert db_call(photos, run_of).status == "done"
    assert matches(photos) == []


def test_other_jobs_name_no_photos(photos: TestClient) -> None:
    async def work(db: Any) -> None:
        asset = await db.scalar(select(Asset).order_by(Asset.local_taken_at))
        await worker_queue.enqueue_module(db, asset, "test")

    db_call(photos, work)
    worker = register(photos)

    assert lease(photos, worker).json()["others"] == []


def test_answers_go_when_the_image_of_a_photo_changes(photos: TestClient) -> None:
    _, second = asset_ids(photos)
    worker = register(photos, modules=["details"])
    enqueue_pairs(photos, [second])
    job = lease(photos, worker, ["details"]).json()
    body = {"module_version": "1", "candidates": [], "pairs": [pair(second)]}
    photos.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)
    assert len(matches(photos)) == 1

    async def forget(db: Any) -> None:
        # The other photo was rotated in Immich: the answer was about its old image.
        await worker_queue.forget_results(db, [second])
        await db.commit()

    db_call(photos, forget)

    assert matches(photos) == []
