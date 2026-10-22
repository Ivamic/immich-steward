# SPDX-License-Identifier: AGPL-3.0-or-later
"""Worker modules seen from the web UI: results in the suggestions, manual and automatic runs."""

import uuid
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

import pytest
from conftest import WORKER_TOKEN, FakeImmich, sync
from fastapi.testclient import TestClient
from sqlalchemy import update

from steward import worker_queue
from steward.api.worker import PROTOCOL_VERSION
from steward.config import Settings
from steward.models import Account, Asset, ModulePause

AUTH = {"Authorization": f"Bearer {WORKER_TOKEN}"}
GPS = {"latitude": 42.4, "longitude": 19.26}
NO_PAUSE = {"all": False, "modules": [], "all_until": None, "until": {}}


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    """File name -> local id."""
    fake_immich.add_asset(taken="2024-05-01T10:00:00", originalFileName="todo1.jpg")
    fake_immich.add_asset(taken="2024-05-01T11:00:00", originalFileName="todo2.jpg")
    fake_immich.add_asset(taken="2024-05-01T12:00:00", originalFileName="gps.jpg", exif=GPS)
    fake_immich.add_asset(taken="2024-05-01T13:00:00", originalFileName="clip.mp4", type="VIDEO")
    fake_immich.add_asset(taken="2024-05-01T14:00:00", originalFileName="skipped.jpg")
    fake_immich.add_asset(
        taken="2024-05-01T15:00:00", originalFileName="archived.jpg", visibility="archive"
    )
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05", "archived": True}).json()
    ids = {item["file_name"]: item["id"] for item in items}
    signed_in.put(f"/api/assets/{ids['skipped.jpg']}/review", json={"status": "skipped"})
    return ids


def geoclip(client: TestClient, asset_id: str) -> dict[str, Any]:
    response = client.get(f"/api/assets/{asset_id}/suggestions")
    assert response.status_code == 200
    module: dict[str, Any] = next(m for m in response.json() if m["module"] == "geoclip")
    return module


def start_worker(client: TestClient, name: str = "gpu") -> dict[str, str]:
    body = {
        "name": name,
        "modules": ["geoclip"],
        "device": "cuda",
        "version": "0.1.0",
        "protocol_version": PROTOCOL_VERSION,
    }
    worker_id = client.post("/api/worker/register", json=body, headers=AUTH).json()["worker_id"]
    return AUTH | {"X-Worker-Id": worker_id}


def schedule(client: TestClient) -> None:
    runner = client.app.state.job_runner  # type: ignore[attr-defined]
    client.portal.call(runner.schedule_modules)  # type: ignore[union-attr]


def finish(client: TestClient, worker: dict[str, str], candidates: list[dict[str, Any]]) -> str:
    job = client.post("/api/worker/lease", json={"modules": ["geoclip"]}, headers=worker).json()
    body = {"module_version": "1", "candidates": candidates}
    client.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)
    return str(job["asset_id"])


def test_not_run_without_a_worker(library: dict[str, str], signed_in: TestClient) -> None:
    module = geoclip(signed_in, library["todo1.jpg"])
    assert module["status"] == "not_run"
    assert module["runnable"] is True
    assert module["worker_available"] is False
    assert module["candidates"] == []
    # M1 is computed on the spot and comes first.
    first = signed_in.get(f"/api/assets/{library['todo1.jpg']}/suggestions").json()[0]
    assert (first["module"], first["status"], first["runnable"]) == (
        "time_neighbors",
        "ready",
        False,
    )


def test_manual_run_goes_first_and_shows_its_result(
    library: dict[str, str], signed_in: TestClient
) -> None:
    worker = start_worker(signed_in)
    schedule(signed_in)  # background runs for all photos to do
    asset = library["todo1.jpg"]
    response = signed_in.post(f"/api/assets/{asset}/modules/geoclip/run")
    assert next(m for m in response.json() if m["module"] == "geoclip")["status"] == "queued"

    area = {"latitude": 41.9, "longitude": 12.5, "score": 0.8, "radius_m": 8000, "kind": "area"}
    others = [
        area | {"latitude": 45.4, "score": 0.6},  # normal
        area | {"latitude": 48.8, "score": 0.3},  # weak: folded in the UI
        area | {"latitude": 50.0, "score": 0.1},  # noise: hidden
    ]
    assert finish(signed_in, worker, [area, *others]) == asset
    module = geoclip(signed_in, asset)
    assert module["status"] == "done"
    assert module["worker_available"] is True
    assert [(c["rank"], c["tier"]) for c in module["candidates"]] == [
        (1, "confident"),
        (2, "normal"),
        (3, "weak"),
    ]
    assert module["candidates"][0]["latitude"] == 41.9
    assert module["finished_at"] is not None

    # Running again replaces the result once the new run is done.
    signed_in.post(f"/api/assets/{asset}/modules/geoclip/run")
    assert geoclip(signed_in, asset)["status"] == "queued"


def test_unknown_module_and_foreign_asset(library: dict[str, str], signed_in: TestClient) -> None:
    asset = library["todo1.jpg"]
    assert signed_in.post(f"/api/assets/{asset}/modules/nope/run").status_code == 404
    missing = "00000000-0000-4000-8000-000000000000"
    assert signed_in.post(f"/api/assets/{missing}/modules/geoclip/run").status_code == 404


def test_automatic_runs_only_with_an_active_worker(
    library: dict[str, str], signed_in: TestClient
) -> None:
    schedule(signed_in)
    assert geoclip(signed_in, library["todo1.jpg"])["status"] == "not_run"

    start_worker(signed_in)
    schedule(signed_in)
    statuses = {name: geoclip(signed_in, i)["status"] for name, i in library.items()}
    # Only photos still to do: not located, not marked, not videos, not archived.
    assert statuses == {
        "todo1.jpg": "queued",
        "todo2.jpg": "queued",
        "gps.jpg": "not_run",
        "clip.mp4": "not_run",
        "skipped.jpg": "not_run",
        "archived.jpg": "not_run",
    }


def test_automatic_runs_never_repeat_and_keep_the_queue_small(
    library: dict[str, str], signed_in: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker_queue, "AUTO_QUEUE_SIZE", 1)
    worker = start_worker(signed_in)
    schedule(signed_in)
    schedule(signed_in)  # the queue is full: nothing more
    queued = [n for n, i in library.items() if geoclip(signed_in, i)["status"] == "queued"]
    assert queued == ["todo2.jpg"]  # newest first

    finish(signed_in, worker, [])
    schedule(signed_in)
    assert geoclip(signed_in, library["todo1.jpg"])["status"] == "queued"
    finish(signed_in, worker, [])
    schedule(signed_in)  # both photos have a run: nothing to queue
    assert {geoclip(signed_in, library[n])["status"] for n in ("todo1.jpg", "todo2.jpg")} == {
        "done"
    }


def test_automatic_runs_can_be_turned_off(library: dict[str, str], signed_in: TestClient) -> None:
    signed_in.app.state.settings.auto_modules = ""  # type: ignore[attr-defined]
    start_worker(signed_in)
    schedule(signed_in)
    assert geoclip(signed_in, library["todo1.jpg"])["status"] == "not_run"


def test_workers_overview(library: dict[str, str], signed_in: TestClient) -> None:
    worker = start_worker(signed_in, "laptop")
    schedule(signed_in)
    finish(signed_in, worker, [])
    overview = signed_in.get("/api/library/workers").json()
    [seen] = overview["workers"]
    assert (seen["name"], seen["device"], seen["active"]) == ("laptop", "cuda", True)
    assert overview["runs"] == {"geoclip": {"done": 1, "queued": 1}}
    assert overview["auto_modules"] == ["geoclip", "similar"]
    assert [m["id"] for m in overview["modules"]] == ["geoclip", "similar"]


def test_goodbye_makes_the_worker_unavailable_and_returns_its_job(
    library: dict[str, str], signed_in: TestClient
) -> None:
    worker = start_worker(signed_in)
    asset = library["todo1.jpg"]
    signed_in.post(f"/api/assets/{asset}/modules/geoclip/run")
    job = signed_in.post("/api/worker/lease", json={"modules": ["geoclip"]}, headers=worker).json()
    assert geoclip(signed_in, asset)["status"] == "running"

    assert signed_in.post("/api/worker/bye", headers=worker).status_code == 204
    module = geoclip(signed_in, asset)
    assert (module["status"], module["worker_available"]) == ("queued", False)
    assert signed_in.get("/api/library/workers").json()["workers"][0]["active"] is False

    # Back again: the job is taken anew, and stopping did not count as a failed attempt.
    start_worker(signed_in)
    again = signed_in.post("/api/worker/lease", json={"modules": ["geoclip"]}, headers=worker)
    assert again.json()["job_id"] == job["job_id"]
    assert again.json()["attempt"] == 1


def test_queue_position(library: dict[str, str], signed_in: TestClient) -> None:
    start_worker(signed_in)
    schedule(signed_in)  # todo2 (newer) and todo1 queued in the background
    assert geoclip(signed_in, library["todo2.jpg"])["queue_position"] == 0
    assert geoclip(signed_in, library["todo1.jpg"])["queue_position"] == 1
    # Started by hand: ahead of the background runs.
    signed_in.post(f"/api/assets/{library['todo1.jpg']}/modules/geoclip/run")
    assert geoclip(signed_in, library["todo1.jpg"])["queue_position"] == 0
    assert geoclip(signed_in, library["todo2.jpg"])["queue_position"] == 1


def test_display_thresholds_are_settings(library: dict[str, str], signed_in: TestClient) -> None:
    worker = start_worker(signed_in)
    asset = library["todo1.jpg"]
    signed_in.post(f"/api/assets/{asset}/modules/geoclip/run")
    finish(signed_in, worker, [{"latitude": 41.9, "longitude": 12.5, "score": 0.1}])
    assert geoclip(signed_in, asset)["candidates"] == []
    # Stored in full: a lower threshold shows it without running GeoCLIP again.
    signed_in.app.state.settings.geoclip_min_confidence = 0.05  # type: ignore[attr-defined]
    [weak] = geoclip(signed_in, asset)["candidates"]
    assert weak["tier"] == "weak"


def test_gallery_filter_for_confident_geoclip_guesses(
    library: dict[str, str], signed_in: TestClient
) -> None:
    worker = start_worker(signed_in)
    point = {"latitude": 41.9, "longitude": 12.5, "kind": "area"}
    scores = {"todo1.jpg": 0.8, "todo2.jpg": 0.6, "gps.jpg": 0.9}
    for name in scores:
        signed_in.post(f"/api/assets/{library[name]}/modules/geoclip/run")
    for _ in scores:
        job = signed_in.post("/api/worker/lease", json={"modules": ["geoclip"]}, headers=worker)
        asset_id = job.json()["asset_id"]
        name = next(n for n, i in library.items() if i == asset_id)
        body = {"module_version": "1", "candidates": [point | {"score": scores[name]}]}
        signed_in.post(f"/api/worker/jobs/{job.json()['job_id']}/result", json=body, headers=worker)

    params = {"month": "2024-05", "geoclip_confident": True}
    items = signed_in.get("/api/assets", params=params).json()
    # Confident enough and still without a location: the photo with GPS is not listed.
    assert [item["file_name"] for item in items] == ["todo1.jpg"]
    months = signed_in.get("/api/assets/months", params={"geoclip_confident": True}).json()
    assert months == [{"month": "2024-05", "count": 1}]
    # Without the filter, the gallery marks the same photo.
    everything = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    marked = {item["file_name"]: item["geoclip_confident"] for item in everything}
    assert marked["todo1.jpg"] is True
    assert marked["todo2.jpg"] is False  # not confident enough
    assert marked["gps.jpg"] is False  # already located


def test_automatic_runs_take_accounts_in_turns(
    library: dict[str, str], signed_in: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another family member's newer photos must not hold back this library."""

    async def add_other_account() -> None:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            other = Account(
                immich_user_id=uuid.uuid4(),
                name="Other",
                email="o@example.com",
                api_key_encrypted="x",
            )
            db.add(other)
            await db.flush()
            for day in (10, 11, 12):  # all newer than this library's photos
                taken = datetime(2025, 1, day, 12)
                db.add(
                    Asset(
                        account_id=other.id,
                        immich_id=uuid.uuid4(),
                        type="IMAGE",
                        visibility="timeline",
                        original_file_name=f"other{day}.jpg",
                        file_created_at=taken,
                        local_taken_at=taken,
                        immich_updated_at=taken,
                        synced_at=taken,
                    )
                )
            await db.commit()

    signed_in.portal.call(add_other_account)  # type: ignore[union-attr]
    monkeypatch.setattr(worker_queue, "AUTO_QUEUE_SIZE", 4)
    worker = start_worker(signed_in)
    schedule(signed_in)

    taken = []
    for _ in range(4):
        job = signed_in.post("/api/worker/lease", json={"modules": ["geoclip"]}, headers=worker)
        taken.append(job.json()["asset_id"] in library.values())
    # Mine, the other's, mine, the other's (or the other way round): never two in a row.
    assert taken.count(True) == 2
    assert all(a != b for a, b in pairwise(taken))


def fail_job(client: TestClient, worker: dict[str, str], body: dict[str, Any] | None = None) -> str:
    job = client.post("/api/worker/lease", json={"modules": ["geoclip"]}, headers=worker).json()
    body = body or {"error": "cannot decode", "retry": False, "code": "image_invalid"}
    client.post(f"/api/worker/jobs/{job['job_id']}/fail", json=body, headers=worker)
    return str(job["asset_id"])


def test_failures_by_reason_filter_and_rerun(
    library: dict[str, str], signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    worker = start_worker(signed_in)
    for name in ("todo1.jpg", "todo2.jpg"):
        signed_in.post(f"/api/assets/{library[name]}/modules/geoclip/run")
    broken = fail_job(signed_in, worker)
    other = fail_job(signed_in, worker, {"error": "boom", "retry": False, "code": "module_error"})

    overview = signed_in.get("/api/library/workers").json()
    assert overview["failures"] == {"geoclip": {"image_invalid": 1, "module_error": 1}}
    assert geoclip(signed_in, broken)["error_code"] == "image_invalid"

    show = ["todo", "with", "skipped", "not_applicable"]
    params: dict[str, Any] = {"month": "2024-05", "show": show, "failed_module": "geoclip"}
    found = signed_in.get("/api/assets", params=params).json()
    assert {item["id"] for item in found} == {broken, other}
    params["failure"] = "image_invalid"
    assert [item["id"] for item in signed_in.get("/api/assets", params=params).json()] == [broken]
    # The card steps through the failed photos only.
    detail = signed_in.get(f"/api/assets/{broken}", params=params).json()
    assert (detail["previous_id"], detail["next_id"]) == (None, None)

    rerun = signed_in.post(
        "/api/library/modules/geoclip/rerun-failed", json={"code": "image_invalid"}
    )
    assert rerun.json() == {"queued": 1}
    assert geoclip(signed_in, broken)["status"] == "queued"
    # The photo no longer counts as failed: its latest run is the new one.
    overview = signed_in.get("/api/library/workers").json()
    assert overview["failures"] == {"geoclip": {"module_error": 1}}
    assert signed_in.get("/api/assets", params=params).json() == []
    assert signed_in.post("/api/library/modules/nope/rerun-failed", json={}).status_code == 404


def test_photo_links_to_immich(library: dict[str, str], signed_in: TestClient) -> None:
    detail = signed_in.get(f"/api/assets/{library['todo1.jpg']}").json()
    assert detail["immich_url"].startswith("http")
    assert "/photos/" in detail["immich_url"]


def test_public_immich_address_wins() -> None:
    internal = Settings(immich_url="http://immich_server:2283/", _env_file=None)
    assert internal.immich_browser_url == "http://immich_server:2283"
    public = Settings(
        immich_url="http://immich_server:2283",
        immich_public_url="https://photos.example.org/",
        _env_file=None,
    )
    assert public.immich_browser_url == "https://photos.example.org"


def test_pause_holds_background_runs_but_not_runs_by_hand(
    library: dict[str, str], signed_in: TestClient
) -> None:
    worker = start_worker(signed_in)

    def take() -> Any:
        return signed_in.post("/api/worker/lease", json={"modules": ["geoclip"]}, headers=worker)

    def pause(**body: Any) -> dict[str, Any]:
        response = signed_in.put("/api/library/pause", json=body)
        assert response.status_code == 200
        result: dict[str, Any] = response.json()
        return result

    assert pause(module="geoclip", paused=True) == NO_PAUSE | {"modules": ["geoclip"]}
    schedule(signed_in)  # nothing is queued for a paused module
    assert geoclip(signed_in, library["todo1.jpg"])["status"] == "not_run"
    assert geoclip(signed_in, library["todo1.jpg"])["paused"] is True
    assert signed_in.get("/api/library/workers").json()["pause"]["modules"] == ["geoclip"]

    # Queued before the pause: waits. Started by hand: goes.
    pause(module="geoclip", paused=False)
    schedule(signed_in)
    pause(module="geoclip", paused=True)
    assert take().status_code == 204
    signed_in.post(f"/api/assets/{library['todo1.jpg']}/modules/geoclip/run")
    assert take().json()["asset_id"] == library["todo1.jpg"]
    assert take().status_code == 204

    # Pausing everything holds them as well; resuming everything lifts both pauses.
    pause(module="geoclip", paused=False)
    assert pause(paused=True) == NO_PAUSE | {"all": True}
    assert take().status_code == 204
    pause(module="geoclip", paused=True)
    assert signed_in.delete("/api/library/pause").json() == NO_PAUSE
    assert take().status_code == 200
    assert geoclip(signed_in, library["todo2.jpg"])["paused"] is False

    assert (
        signed_in.put("/api/library/pause", json={"module": "nope", "paused": True}).status_code
        == 404
    )


def test_worker_state_is_shown(library: dict[str, str], signed_in: TestClient) -> None:
    worker = start_worker(signed_in)

    def say(state: str, module: str | None = None) -> None:
        body = {"state": state, "module": module}
        assert signed_in.post("/api/worker/state", json=body, headers=worker).status_code == 204

    def shown() -> dict[str, Any]:
        result: dict[str, Any] = signed_in.get("/api/library/workers").json()["workers"][0]
        return result

    assert shown()["state"] is None  # registered, has said nothing yet
    say("loading", "geoclip")
    since = shown()["state_since"]
    assert (shown()["state"], shown()["state_module"]) == ("loading", "geoclip")
    assert geoclip(signed_in, library["todo1.jpg"])["worker_loading"] is True
    say("loading", "geoclip")
    assert shown()["state_since"] == since  # the time counts from the change
    say("working", "geoclip")
    assert geoclip(signed_in, library["todo1.jpg"])["worker_loading"] is False

    bad = {"state": "dancing", "module": None}
    assert signed_in.post("/api/worker/state", json=bad, headers=worker).status_code == 422
    signed_in.post("/api/worker/bye", headers=worker)
    assert shown()["state"] is None


def test_pause_for_a_while_ends_by_itself(library: dict[str, str], signed_in: TestClient) -> None:
    worker = start_worker(signed_in)
    schedule(signed_in)

    def take() -> int:
        body = {"modules": ["geoclip"]}
        return signed_in.post("/api/worker/lease", json=body, headers=worker).status_code

    body = {"module": "geoclip", "paused": True, "minutes": 30}
    pause = signed_in.put("/api/library/pause", json=body).json()
    assert pause["modules"] == ["geoclip"]
    until = datetime.fromisoformat(pause["until"]["geoclip"])
    assert 29 * 60 < (until - datetime.now(UTC)).total_seconds() <= 30 * 60
    assert take() == 204

    async def over() -> None:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            ended = datetime.now(UTC) - timedelta(seconds=1)
            await db.execute(update(ModulePause).values(until=ended))
            await db.commit()

    signed_in.portal.call(over)  # type: ignore[union-attr]
    assert signed_in.get("/api/library/pause").json() == NO_PAUSE
    assert take() == 200

    # Pausing again replaces the end: for a while, then until resumed.
    signed_in.put("/api/library/pause", json={"paused": True, "minutes": 60})
    assert signed_in.get("/api/library/pause").json()["all_until"] is not None
    signed_in.put("/api/library/pause", json={"paused": True})
    assert signed_in.get("/api/library/pause").json() == NO_PAUSE | {"all": True}
    too_long = {"paused": True, "minutes": 8 * 24 * 60}
    assert signed_in.put("/api/library/pause", json=too_long).status_code == 422
