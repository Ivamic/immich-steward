# SPDX-License-Identifier: AGPL-3.0-or-later
"""The badge "similar with a location" of the gallery, computed in the background."""

from datetime import timedelta
from typing import Any

import pytest
from conftest import FakeImmich, run_jobs, sync
from fastapi.testclient import TestClient
from test_embeddings import encoded, run_module, start_worker, unit

from steward import locations, similar_hints

GPS = {"latitude": 42.4, "longitude": 19.26}


@pytest.fixture(autouse=True)
def fast_clear_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locations, "CLEAR_POLL_S", 0.0)


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    """File name -> id in the app; every photo has its vector."""
    vectors = {"gps.jpg": unit(0), "alike.jpg": unit(0), "other.jpg": unit(5)}
    for hour, name in enumerate(vectors):
        exif = {"exif": GPS} if name == "gps.jpg" else {}
        fake_immich.add_asset(taken=f"2024-05-01T{10 + hour}:00:00", originalFileName=name, **exif)
    sync(signed_in)
    ids = items_by_name(signed_in)
    worker = start_worker(signed_in)
    for name, vector in vectors.items():
        run_module(signed_in, worker, ids[name]["id"], {"embedding": encoded(vector)})
    return {name: item["id"] for name, item in ids.items()}


def items_by_name(client: TestClient, **params: Any) -> dict[str, dict[str, Any]]:
    items = client.get("/api/assets", params={"month": "2024-05"} | params).json()
    return {item["file_name"]: item for item in items}


def badges(client: TestClient) -> dict[str, bool]:
    return {name: item["similar_confident"] for name, item in items_by_name(client).items()}


def schedule(client: TestClient) -> None:
    runner = client.app.state.job_runner  # type: ignore[attr-defined]
    portal = client.portal
    assert portal is not None
    portal.call(runner.schedule_similar_hints)
    run_jobs(client)


@pytest.mark.usefixtures("library")
def test_the_badge_after_a_full_pass(signed_in: TestClient) -> None:
    assert not any(badges(signed_in).values())  # nothing computed yet

    job = signed_in.post("/api/library/similar-hints")
    assert job.status_code == 202
    run_jobs(signed_in)

    # Only a photo without a location gets it, and only when the similar one is close enough.
    assert badges(signed_in) == {"gps.jpg": False, "alike.jpg": True, "other.jpg": False}
    library = signed_in.get("/api/library").json()
    assert library["similar_hints_at"] is not None
    assert library["similar_hints_job"]["progress"] == {
        "full": True,
        "photos": 2,
        "confident": 1,
        "left": 0,
    }
    # The filter of the gallery.
    assert list(items_by_name(signed_in, similar_confident=True)) == ["alike.jpg"]


def test_a_long_pass_lets_other_jobs_through(
    signed_in: TestClient, library: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(similar_hints, "BATCH", 1)
    monkeypatch.setattr(similar_hints, "SEARCH_FOR", timedelta(0))
    assert signed_in.post("/api/library/similar-hints").status_code == 202
    # Something else asked for while a slice runs goes before the rest of the pass.
    signed_in.post("/api/library/sync", json={"full": None})
    runner = signed_in.app.state.job_runner  # type: ignore[attr-defined]
    assert signed_in.portal.call(runner.run_once)  # type: ignore[union-attr]
    assert signed_in.portal.call(runner.run_once)  # type: ignore[union-attr]
    library_now = signed_in.get("/api/library").json()
    assert library_now["sync_job"]["status"] == "done"
    assert library_now["similar_hints_job"]["status"] == "queued"

    run_jobs(signed_in)
    done = signed_in.get("/api/library").json()["similar_hints_job"]
    assert done["progress"] == {"full": True, "photos": 2, "confident": 1, "left": 0}
    assert badges(signed_in) == {"gps.jpg": False, "alike.jpg": True, "other.jpg": False}


def test_new_vectors_are_done_in_between(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    schedule(signed_in)  # the first pass is a full one
    fake_immich.add_asset(taken="2024-05-01T20:00:00", originalFileName="new.jpg")
    sync(signed_in, full=True)
    new_id = items_by_name(signed_in)["new.jpg"]["id"]
    run_module(signed_in, start_worker(signed_in), new_id, {"embedding": encoded(unit(0))})

    schedule(signed_in)

    assert badges(signed_in)["new.jpg"] is True
    job = signed_in.get("/api/library").json()["similar_hints_job"]
    assert job["progress"] == {"full": False, "photos": 1, "confident": 1, "left": 0}


def test_a_located_photo_loses_the_badge(signed_in: TestClient, library: dict[str, str]) -> None:
    schedule(signed_in)
    assert badges(signed_in)["alike.jpg"] is True

    point = {"latitude": 43.0, "longitude": 20.0}
    response = signed_in.put(f"/api/assets/{library['alike.jpg']}/location", json=point)
    assert response.status_code == 200

    assert badges(signed_in)["alike.jpg"] is False
