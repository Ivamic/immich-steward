# SPDX-License-Identifier: AGPL-3.0-or-later
"""When the comparisons of details run: by themselves on a GPU, by hand anywhere (D-226)."""

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_details_confirm import compared
from test_embeddings import AUTH
from test_similar_search import library  # noqa: F401
from test_worker_api import db_call

from steward import details, worker_queue
from steward.api.worker import PROTOCOL_VERSION
from steward.models import Asset, Job, ModuleRun

Library = dict[str, str]


def worker_on(client: TestClient, device: str, name: str = "w-details") -> dict[str, str]:
    body = {
        "name": name,
        "modules": ["details"],
        "device": device,
        "version": "0.11.0",
        "protocol_version": PROTOCOL_VERSION,
    }
    worker_id = client.post("/api/worker/register", json=body, headers=AUTH).json()["worker_id"]
    return AUTH | {"X-Worker-Id": worker_id}


def lease(client: TestClient, worker: dict[str, str]) -> Any:
    return client.post("/api/worker/lease", json={"modules": ["details"]}, headers=worker)


def auto(client: TestClient) -> int:
    async def work(db: Any) -> int:
        return await details.auto_enqueue(db, client.app.state.settings)  # type: ignore[attr-defined]

    result: int = db_call(client, work)
    return result


def detail_runs(client: TestClient) -> list[tuple[str, str, int]]:
    """File name, status and number of photos named, of every run of the module."""

    async def work(db: Any) -> list[tuple[str, str, int]]:
        rows = await db.execute(
            select(Asset.original_file_name, ModuleRun.status, ModuleRun.job_id)
            .join(Asset, Asset.id == ModuleRun.asset_id)
            .where(ModuleRun.module_id == "details")
            .order_by(Asset.original_file_name)
        )
        found = []
        for name, status, job_id in rows:
            job = await db.get(Job, job_id) if job_id else None
            found.append((name, status, len(worker_queue.others_of(job)) if job else 0))
        return found

    result: list[tuple[str, str, int]] = db_call(client, work)
    return result


def test_photos_without_a_location_are_queued_once(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    # query.jpg is the only photo without a location: five photos with one are similar to it.
    assert auto(signed_in) == 1
    assert detail_runs(signed_in) == [("query.jpg", "queued", 5)]
    assert auto(signed_in) == 0


def test_the_number_of_photos_compared_is_a_personal_setting(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    assert signed_in.put("/api/settings", json={"details_candidates_auto": 2}).is_success

    auto(signed_in)

    assert detail_runs(signed_in) == [("query.jpg", "queued", 2)]


def test_a_photo_with_nothing_to_compare_with_is_not_looked_at_again(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    for name in ("kotor.jpg", "kotor-near.jpg", "budva.jpg", "paris.jpg", "set-by-app.jpg"):
        compared(signed_in, library["query.jpg"], library[name], 15)

    assert auto(signed_in) == 0
    assert detail_runs(signed_in) == [("query.jpg", "done", 0)]
    assert auto(signed_in) == 0


def test_only_a_worker_with_a_gpu_takes_the_comparisons_queued_by_themselves(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    auto(signed_in)

    assert lease(signed_in, worker_on(signed_in, "cpu", "server")).status_code == 204
    job = lease(signed_in, worker_on(signed_in, "cuda", "laptop")).json()
    assert (job["module"], len(job["others"])) == ("details", 5)


def test_a_comparison_started_by_hand_runs_on_any_worker(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query = library["query.jpg"]

    assert signed_in.post(f"/api/assets/{query}/modules/details/run").is_success

    # Five by default, most similar first.
    job = lease(signed_in, worker_on(signed_in, "cpu")).json()
    assert job["asset_id"] == query
    assert job["others"] == [
        library[name]
        for name in ("set-by-app.jpg", "kotor.jpg", "kotor-near.jpg", "budva.jpg", "paris.jpg")
    ]


def test_started_by_hand_it_goes_before_the_queue_and_keeps_the_longer_list(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    signed_in.put("/api/settings", json={"details_candidates_manual": 2})
    auto(signed_in)
    query = library["query.jpg"]

    signed_in.post(f"/api/assets/{query}/modules/details/run")

    # The same run, now urgent: a worker without a GPU takes it.
    assert [(name, status) for name, status, _ in detail_runs(signed_in)] == [
        ("query.jpg", "queued")
    ]
    job = lease(signed_in, worker_on(signed_in, "cpu")).json()
    assert job["asset_id"] == query
    assert len(job["others"]) == 5


def test_nothing_to_compare_with_queues_nothing(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    # A photo with a location has similar photos too, but every one of them compared already.
    kotor = library["kotor.jpg"]
    for name in ("query.jpg", "kotor-near.jpg", "budva.jpg", "paris.jpg", "set-by-app.jpg"):
        if name != "query.jpg":
            compared(signed_in, kotor, library[name], 10)

    assert signed_in.post(f"/api/assets/{kotor}/modules/details/run").is_success
    assert detail_runs(signed_in) == []


def test_someone_elses_photo_is_not_found(signed_in: TestClient) -> None:
    unknown = UUID(int=1)

    assert signed_in.post(f"/api/assets/{unknown}/modules/details/run").status_code == 404
