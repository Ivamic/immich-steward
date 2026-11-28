# SPDX-License-Identifier: AGPL-3.0-or-later
"""When the comparisons of details run: by themselves on a GPU, by hand anywhere (D-226)."""

from typing import Any
from uuid import UUID

from conftest import sync
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_details_confirm import compared
from test_embeddings import AUTH, encoded, run_module, start_worker
from test_similar_search import ROME, library, similar_to_query  # noqa: F401
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


# --- What the card is told ---


def similar_block(client: TestClient, asset_id: str) -> dict[str, Any]:
    blocks = client.get(f"/api/assets/{asset_id}/suggestions").json()
    block: dict[str, Any] = next(b for b in blocks if b["key"] == "similar")
    return block


def test_the_card_knows_the_state_of_the_comparison(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query = library["query.jpg"]
    assert similar_block(signed_in, query)["details"] == {
        "status": "not_run",
        "worker_available": False,
        "queue_position": None,
        "urgent": False,
    }

    worker = worker_on(signed_in, "cpu")
    signed_in.post(f"/api/assets/{query}/modules/details/run")
    assert similar_block(signed_in, query)["details"] == {
        "status": "queued",
        "worker_available": True,
        "queue_position": 0,
        "urgent": True,
    }

    job = lease(signed_in, worker).json()
    assert similar_block(signed_in, query)["details"]["status"] == "running"
    body = {"module_version": "1", "candidates": [], "pairs": []}
    signed_in.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)
    assert similar_block(signed_in, query)["details"]["status"] == "done"

    # Only similar photos are confirmed by details.
    others = signed_in.get(f"/api/assets/{query}/suggestions").json()
    assert all(b["details"] is None for b in others if b["key"] != "similar")


def test_the_shared_points_of_a_pair_from_either_photo(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query, budva, kotor = (library[n] for n in ("query.jpg", "budva.jpg", "kotor.jpg"))

    async def work(db: Any) -> None:
        from steward.models import DetailMatch

        db.add(
            DetailMatch(
                asset_id=UUID(query),
                other_id=UUID(budva),
                matches=300,
                inliers=150,
                lines=[[0.1, 0.2, 0.3, 0.4]],
                module_version="1",
            )
        )
        await db.commit()

    db_call(signed_in, work)

    assert signed_in.get(f"/api/assets/{query}/details/{budva}").json() == {
        "matches": 300,
        "inliers": 150,
        "lines": [[0.1, 0.2, 0.3, 0.4]],
    }
    assert signed_in.get(f"/api/assets/{budva}/details/{query}").json()["lines"] == [
        [0.3, 0.4, 0.1, 0.2]
    ]
    missing = signed_in.get(f"/api/assets/{query}/details/{kotor}")
    assert (missing.status_code, missing.json()["code"]) == (404, "details_not_compared")


def test_a_comparison_queued_by_itself_can_be_moved_ahead_from_the_card(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query = library["query.jpg"]
    auto(signed_in)

    # Waiting its turn, with no worker with a GPU around.
    waiting = similar_block(signed_in, query)["details"]
    assert (waiting["status"], waiting["urgent"], waiting["queue_position"]) == ("queued", False, 0)

    signed_in.post(f"/api/assets/{query}/modules/details/run")

    assert similar_block(signed_in, query)["details"]["urgent"] is True
    assert lease(signed_in, worker_on(signed_in, "cpu")).json()["asset_id"] == query


# --- A second look a day later ---


def a_day_passed(client: TestClient) -> None:
    """Every comparison so far was made a day and an hour ago."""

    async def work(db: Any) -> None:
        from datetime import timedelta

        from sqlalchemy import update

        ago = timedelta(hours=25)
        await db.execute(
            update(ModuleRun)
            .where(ModuleRun.module_id == "details")
            .values(created_at=ModuleRun.created_at - ago, finished_at=ModuleRun.finished_at - ago)
        )
        await db.commit()

    db_call(client, work)


def finish(client: TestClient, pairs: dict[str, int]) -> None:
    """A worker with a GPU takes the next comparison and answers with these shared details."""
    worker = worker_on(client, "cuda", "gpu")
    job = lease(client, worker).json()
    body = {
        "module_version": "1",
        "candidates": [],
        "pairs": [
            {"other": other, "matches": 2 * count, "inliers": count, "lines": []}
            for other, count in pairs.items()
            if other in job["others"]
        ],
    }
    assert client.post(
        f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker
    ).is_success


def test_a_photo_started_by_hand_gets_the_rest_of_its_similar_photos_a_day_later(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    signed_in.put("/api/settings", json={"details_candidates_manual": 2})
    query = library["query.jpg"]
    signed_in.post(f"/api/assets/{query}/modules/details/run")
    finish(signed_in, {library["set-by-app.jpg"]: 20, library["kotor.jpg"]: 30})

    # Compared a moment ago: not looked at again yet.
    assert auto(signed_in) == 0

    a_day_passed(signed_in)
    assert auto(signed_in) == 1
    # The three it was not compared with, of its five similar photos.
    assert detail_runs(signed_in)[-1] == ("query.jpg", "queued", 3)


def test_a_confirmed_photo_is_not_compared_with_more(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    signed_in.put("/api/settings", json={"details_candidates_manual": 2})
    query = library["query.jpg"]
    signed_in.post(f"/api/assets/{query}/modules/details/run")
    finish(signed_in, {library["set-by-app.jpg"]: 20, library["kotor.jpg"]: 180})
    a_day_passed(signed_in)

    assert auto(signed_in) == 0
    assert [status for _, status, _ in detail_runs(signed_in)] == ["done"]
    # Noted as looked at: the next pass leaves it alone too.
    assert auto(signed_in) == 0


def test_a_photo_with_nothing_new_to_compare_with_waits_another_day(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query = library["query.jpg"]
    for name in ("kotor.jpg", "kotor-near.jpg", "budva.jpg", "paris.jpg", "set-by-app.jpg"):
        compared(signed_in, query, library[name], 15)
    assert auto(signed_in) == 0
    a_day_passed(signed_in)

    # Looked at again, nothing new: one run still, and the next pass leaves the photo alone.
    assert auto(signed_in) == 0
    assert detail_runs(signed_in) == [("query.jpg", "done", 0)]
    assert auto(signed_in) == 0


def located_newly(client: TestClient, fake_immich: Any) -> str:
    """A photo like query.jpg, without a location at first; its vector found. Returns its id."""
    fake_immich.add_asset(taken="2024-05-01T20:00:00", originalFileName="new.jpg")
    sync(client, full=True)
    items = client.get("/api/assets", params={"month": "2024-05"}).json()
    new = next(item["id"] for item in items if item["file_name"] == "new.jpg")
    worker = start_worker(client)
    vector = similar_to_query(0.9, 7)
    assert run_module(client, worker, new, {"embedding": encoded(vector)}).is_success
    return str(new)


def test_a_location_saved_looks_again_at_the_photos_like_it(
    signed_in: TestClient,
    fake_immich: Any,
    library: Library,  # noqa: F811
) -> None:
    # query.jpg was compared with every photo with a location: nothing to do for it now.
    for name in ("kotor.jpg", "kotor-near.jpg", "budva.jpg", "paris.jpg", "set-by-app.jpg"):
        compared(signed_in, library["query.jpg"], library[name], 5)
    new = located_newly(signed_in, fake_immich)

    # A photo like it gets a location: it is compared at once, not a day later.
    assert signed_in.put(f"/api/assets/{new}/location", json=ROME).is_success

    assert detail_runs(signed_in) == [("query.jpg", "queued", 1)]


def test_without_the_comparison_by_itself_a_location_queues_nothing(
    signed_in: TestClient,
    fake_immich: Any,
    library: Library,  # noqa: F811
) -> None:
    app_settings = signed_in.app.state.settings  # type: ignore[attr-defined]
    signed_in.app.state.settings = app_settings.model_copy(  # type: ignore[attr-defined]
        update={"auto_modules": "geoclip,similar"}
    )
    new = located_newly(signed_in, fake_immich)

    assert signed_in.put(f"/api/assets/{new}/location", json=ROME).is_success

    assert detail_runs(signed_in) == []


def test_a_video_waits_for_the_comparison_like_a_photo() -> None:
    """By its preview (0.15): the details compare videos too; GeoCLIP and the orientation do not."""

    def waiting(kind: str) -> bool:
        return details._waits(
            Asset(
                latitude=None,
                review_status="new",
                visibility="timeline",
                type=kind,
                is_trashed=False,
            )
        )

    assert waiting("IMAGE") and waiting("VIDEO")
    assert worker_queue.asset_types("details") == ("IMAGE", "VIDEO")
    assert worker_queue.asset_types("geoclip") == ("IMAGE",)
    assert worker_queue.asset_types("orientation") == ("IMAGE",)
