# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turned photos (D-237): the answers of the `orientation` module and the list to turn back."""

from typing import Any

import pytest
from conftest import WORKER_TOKEN, FakeImmich, sync
from fastapi.testclient import TestClient

from steward import worker_queue
from steward.api.worker import PROTOCOL_VERSION

AUTH = {"Authorization": f"Bearer {WORKER_TOKEN}"}
GPS = {"latitude": 42.4, "longitude": 19.26}
URL = "/api/groups/candidates/turned"
UPRIGHT = [0.9, 0.04, 0.03, 0.03]
LEFT = [0.02, 0.925, 0.03, 0.025]  # turned 90 degrees counter-clockwise: needs 90 clockwise
RIGHT = [0.03, 0.03, 0.02, 0.92]
UPSIDE_DOWN = [0.02, 0.03, 0.93, 0.02]
UNSURE = [0.1, 0.85, 0.03, 0.02]


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    """File name -> local id."""
    for hour, name in enumerate(["a", "b", "c", "d", "e"], start=10):
        fake_immich.add_asset(taken=f"2024-05-01T{hour}:00:00", originalFileName=f"{name}.jpg")
    fake_immich.add_asset(taken="2024-05-01T16:00:00", originalFileName="gps.jpg", exif=GPS)
    fake_immich.add_asset(
        taken="2024-05-01T17:00:00", originalFileName="old.jpg", visibility="archive"
    )
    fake_immich.add_asset(taken="2024-05-01T18:00:00", originalFileName="clip.mp4", type="VIDEO")
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
        "modules": ["orientation"],
        "device": "cuda",
        "version": "0.13.0",
        "protocol_version": PROTOCOL_VERSION,
    }
    worker_id = client.post("/api/worker/register", json=body, headers=AUTH).json()["worker_id"]
    return AUTH | {"X-Worker-Id": worker_id}


def schedule(client: TestClient) -> None:
    runner = client.app.state.job_runner  # type: ignore[attr-defined]
    client.portal.call(runner.schedule_modules)  # type: ignore[union-attr]


def answer_all(client: TestClient, worker: dict[str, str], answers: dict[str, list[float]]) -> None:
    """Leases every queued job and answers by the photo's id (upright when not named)."""
    while True:
        lease = client.post("/api/worker/lease", json={"modules": ["orientation"]}, headers=worker)
        if lease.status_code == 204:
            return
        job = lease.json()
        body = {
            "module_version": "1",
            "candidates": [],
            "orientation": {"probs": answers.get(job["asset_id"], UPRIGHT), "looks": 4},
        }
        done = client.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)
        assert done.status_code == 204


def turned(client: TestClient, **params: Any) -> dict[int, list[str]]:
    response = client.get(URL, params=params)
    assert response.status_code == 200
    return {g["turn"]: [p["file_name"] for p in g["photos"]] for g in response.json()["groups"]}


def test_every_photo_is_looked_at_and_the_turned_ones_listed(
    library: dict[str, str], signed_in: TestClient
) -> None:
    worker = start_worker(signed_in)
    schedule(signed_in)
    answer_all(
        signed_in,
        worker,
        {
            library["a.jpg"]: LEFT,
            library["b.jpg"]: RIGHT,
            library["c.jpg"]: UPSIDE_DOWN,
            library["d.jpg"]: UNSURE,
            library["gps.jpg"]: LEFT,
            library["old.jpg"]: RIGHT,
        },
    )
    data = signed_in.get(URL).json()
    # Also photos with a location and archived ones; not videos.
    assert data["checked"] == 7
    # Upside down is off by default; the unsure one is below the threshold.
    assert turned(signed_in) == {1: ["gps.jpg", "a.jpg"], 3: ["old.jpg", "b.jpg"]}
    groups = {g["turn"]: g for g in data["groups"]}
    assert (groups[1]["fix"], groups[3]["fix"]) == (90, 270)
    assert groups[1]["total"] == 2
    assert groups[1]["scores"] == [0.925, 0.925]

    signed_in.app.state.settings.orientation_upside_down = True  # type: ignore[attr-defined]
    assert turned(signed_in, turn=2) == {2: ["c.jpg"]}
    signed_in.app.state.settings.orientation_min_confidence = 0.8  # type: ignore[attr-defined]
    assert "d.jpg" in turned(signed_in)[1]


def test_kept_photos_leave_the_list_and_can_come_back(
    library: dict[str, str], signed_in: TestClient
) -> None:
    worker = start_worker(signed_in)
    schedule(signed_in)
    answer_all(signed_in, worker, {library["a.jpg"]: LEFT, library["b.jpg"]: LEFT})
    keep = {"ids": [library["a.jpg"]], "kept": True}
    assert signed_in.post(f"{URL}/keep", json=keep).json() == {"changed": 1}
    assert turned(signed_in) == {1: ["b.jpg"], 3: []}

    again = {"ids": [library["a.jpg"]], "kept": False}
    assert signed_in.post(f"{URL}/keep", json=again).json() == {"changed": 1}
    assert turned(signed_in)[1] == ["b.jpg", "a.jpg"]


def test_a_turned_photo_is_looked_at_again(library: dict[str, str], signed_in: TestClient) -> None:
    worker = start_worker(signed_in)
    schedule(signed_in)
    answer_all(signed_in, worker, {library["a.jpg"]: LEFT})
    assert turned(signed_in)[1] == ["a.jpg"]

    # Turned in Immich (or here): the old answer goes with the run, and the photo is queued anew.
    async def work(db: Any) -> None:
        import uuid

        await worker_queue.forget_results(db, [uuid.UUID(library["a.jpg"])])
        await db.commit()

    db_call(signed_in, work)
    assert turned(signed_in)[1] == []
    schedule(signed_in)
    answer_all(signed_in, worker, {})
    assert signed_in.get(URL).json()["checked"] == 7


def test_an_answer_must_be_four_chances(library: dict[str, str], signed_in: TestClient) -> None:
    worker = start_worker(signed_in)
    schedule(signed_in)
    job = signed_in.post(
        "/api/worker/lease", json={"modules": ["orientation"]}, headers=worker
    ).json()
    url = f"/api/worker/jobs/{job['job_id']}/result"
    for bad in [None, {"probs": [0.5, 0.5]}, {"probs": [2, 0, 0, 0]}]:
        body: dict[str, Any] = {"module_version": "1", "candidates": [], "orientation": bad}
        response = signed_in.post(url, json=body, headers=worker)
        assert response.status_code == 422, bad
