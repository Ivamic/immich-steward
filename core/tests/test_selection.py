# SPDX-License-Identifier: AGPL-3.0-or-later
"""Actions on several photos chosen in the gallery (D-149)."""

from typing import Any

import pytest
from conftest import FakeImmich, run_jobs, sync
from fastapi.testclient import TestClient
from test_module_runs import finish, start_worker

from steward import jobs, locations, rotation

KOTOR = {"latitude": 42.4247, "longitude": 18.7712}
BUDVA = {"latitude": 42.2864, "longitude": 18.84}
# About 30 m from Budva: the same place.
BUDVA_NEAR = {"latitude": 42.2866, "longitude": 18.8402}
TAG = "steward/estimated"
ROTATE_90 = {"action": "rotate", "parameters": {"angle": 90}}


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locations, "CLEAR_POLL_S", 0.0)
    monkeypatch.setattr(rotation, "THUMBNAIL_POLL_S", 0.0)


@pytest.fixture
def photos(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, tuple[str, str]]:
    """Name -> (local id, Immich id), in the order of time."""
    immich_ids = {
        "before": fake_immich.add_asset(taken="2024-05-01T08:00:00", exif=KOTOR),
        "a": fake_immich.add_asset(taken="2024-05-01T10:00:00"),
        "b": fake_immich.add_asset(taken="2024-05-01T10:05:00"),
        "located": fake_immich.add_asset(taken="2024-05-01T10:10:00", exif=BUDVA),
        "near": fake_immich.add_asset(taken="2024-05-01T10:15:00", exif=BUDVA_NEAR),
        "clip": fake_immich.add_asset(taken="2024-05-01T10:20:00", type="VIDEO"),
        "after": fake_immich.add_asset(taken="2024-05-01T11:00:00", exif=BUDVA),
    }
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05", "show": "with"}).json()
    items += signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    by_name = {item["file_name"]: item["id"] for item in items}
    return {
        name: (by_name[fake_immich.assets[immich_id]["originalFileName"]], immich_id)
        for name, immich_id in immich_ids.items()
    }


def ids(photos: dict[str, tuple[str, str]], *names: str) -> list[str]:
    return [photos[name][0] for name in names]


def point(fake_immich: FakeImmich, immich_id: str) -> tuple[float | None, float | None]:
    exif = fake_immich.assets[immich_id]["exifInfo"]
    return exif.get("latitude"), exif.get("longitude")


def write(client: TestClient, asset_ids: list[str], overwrite: bool = False) -> Any:
    body = {"ids": asset_ids, **KOTOR, "overwrite": overwrite}
    return client.post("/api/selection/location", json=body)


def test_location_for_several_photos_leaves_located_ones(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    response = write(signed_in, ids(photos, "a", "b", "located"))
    assert response.status_code == 200
    result = response.json()
    assert (result["written"], result["skipped_located"]) == (2, 1)
    assert fake_immich.bulk_location_writes == 1
    for name in ("a", "b"):
        assert point(fake_immich, photos[name][1]) == (KOTOR["latitude"], KOTOR["longitude"])
        assert fake_immich.tag_values(photos[name][1]) == {TAG}
    assert point(fake_immich, photos["located"][1]) == (BUDVA["latitude"], BUDVA["longitude"])
    detail = signed_in.get(f"/api/assets/{photos['a'][0]}").json()
    assert detail["latitude"] == KOTOR["latitude"]
    assert detail["can_undo"] is True


def test_nothing_to_write_when_all_are_located(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    result = write(signed_in, ids(photos, "located")).json()
    assert result == {"batch_id": None, "written": 0, "skipped_located": 1}
    assert fake_immich.bulk_location_writes == 0


def test_overwrite_and_undo_the_batch(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    result = write(signed_in, ids(photos, "a", "located"), overwrite=True).json()
    assert result["written"] == 2
    assert point(fake_immich, photos["located"][1]) == (KOTOR["latitude"], KOTOR["longitude"])

    response = signed_in.post("/api/selection/location/undo", json={"batch_id": result["batch_id"]})
    assert response.status_code == 200
    assert response.json() == {"undone": 2, "changed": 0, "failed": 0}
    assert point(fake_immich, photos["a"][1]) == (None, None)
    assert point(fake_immich, photos["located"][1]) == (BUDVA["latitude"], BUDVA["longitude"])
    assert fake_immich.tag_values(photos["a"][1]) == set()
    assert signed_in.get(f"/api/assets/{photos['a'][0]}").json()["latitude"] is None

    again = signed_in.post("/api/selection/location/undo", json={"batch_id": result["batch_id"]})
    assert (again.status_code, again.json()["code"]) == (409, "location_nothing_to_undo")


def test_undo_leaves_what_changed_since(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    result = write(signed_in, ids(photos, "a", "b")).json()
    # Someone moved one photo in Immich; another was saved again here.
    fake_immich.assets[photos["a"][1]]["exifInfo"] |= BUDVA
    signed_in.put(f"/api/assets/{photos['b'][0]}/location", json=BUDVA_NEAR)

    undone = signed_in.post("/api/selection/location/undo", json={"batch_id": result["batch_id"]})
    assert undone.json() == {"undone": 0, "changed": 2, "failed": 0}
    assert point(fake_immich, photos["a"][1]) == (BUDVA["latitude"], BUDVA["longitude"])
    assert point(fake_immich, photos["b"][1]) == (
        BUDVA_NEAR["latitude"],
        BUDVA_NEAR["longitude"],
    )


def test_review_for_several_photos(
    signed_in: TestClient, photos: dict[str, tuple[str, str]]
) -> None:
    body = {"ids": ids(photos, "a", "b"), "status": "not_applicable"}
    assert signed_in.put("/api/selection/review", json=body).json() == {"changed": 2}
    assert signed_in.put("/api/selection/review", json=body).json() == {"changed": 0}
    todo = signed_in.get("/api/assets", params={"month": "2024-05", "show": "todo"}).json()
    assert not {photos["a"][0], photos["b"][0]} & {item["id"] for item in todo}


def test_foreign_or_unknown_photos(signed_in: TestClient) -> None:
    body = {"ids": ["00000000-0000-0000-0000-000000000000"], **KOTOR}
    response = signed_in.post("/api/selection/location", json=body)
    assert (response.status_code, response.json()["code"]) == (404, "asset_not_found")
    assert signed_in.post("/api/selection/suggestions", json={"ids": []}).status_code == 422


def rotate(client: TestClient, asset_ids: list[str], turn: int = 90) -> dict[str, Any]:
    response = client.post("/api/selection/rotate", json={"ids": asset_ids, "turn": turn})
    assert response.status_code == 200
    job: dict[str, Any] = response.json()
    return job


def test_rotate_several_photos_in_the_background(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    job = rotate(signed_in, ids(photos, "a", "b", "clip"))
    assert job["status"] == "queued"
    run_jobs(signed_in)

    done = signed_in.get(f"/api/selection/jobs/{job['id']}").json()
    assert done["status"] == "done"
    progress = done["progress"]
    assert (progress["total"], progress["done"], progress["videos"], progress["failed"]) == (
        2,
        2,
        1,
        0,
    )
    for name in ("a", "b"):
        assert fake_immich.edits[photos[name][1]] == [ROTATE_90]
    assert photos["clip"][1] not in fake_immich.edits
    # New thumbnails: the gallery asks for them at new addresses.
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    versions = {item["id"]: item["version"] for item in items}
    assert versions[photos["a"][0]].startswith("edited-")


def test_rotation_run_again_does_not_turn_twice(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    job = rotate(signed_in, ids(photos, "a", "b"))
    # As if the core stopped after turning the first photo.
    runner = signed_in.app.state.job_runner  # type: ignore[attr-defined]

    async def turned_first() -> None:
        async with runner._sessionmaker() as db:
            found = await db.get(jobs.Job, job["id"])
            found.progress = {"done_ids": [photos["a"][0]]}
            await db.commit()

    signed_in.portal.call(turned_first)  # type: ignore[union-attr]
    run_jobs(signed_in)
    assert photos["a"][1] not in fake_immich.edits
    assert fake_immich.edits[photos["b"][1]] == [ROTATE_90]
    progress = signed_in.get(f"/api/selection/jobs/{job['id']}").json()["progress"]
    assert progress["done"] == 2


def test_rotation_without_the_edit_permissions_fails_the_job(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    fake_immich.can_edit = False
    job = rotate(signed_in, ids(photos, "a"))
    run_jobs(signed_in)
    done = signed_in.get(f"/api/selection/jobs/{job['id']}").json()
    assert (done["status"], done["error"]) == ("failed", "immich_missing_permissions")


def blocks(client: TestClient, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
    response = client.post("/api/selection/suggestions", json={"ids": asset_ids})
    assert response.status_code == 200
    return {block["module"]: block for block in response.json()}


def test_suggestions_from_the_chosen_and_their_neighbors(
    signed_in: TestClient, photos: dict[str, tuple[str, str]]
) -> None:
    found = blocks(signed_in, ids(photos, "a", "b", "located", "near"))
    assert next(iter(found)) == "selection"

    [same] = found["selection"]["candidates"]
    assert same["kind"] == "selected"
    assert same["evidence"]["photos"] == 2
    assert same["score"] == 1.0

    neighbors = found["time_neighbors"]
    kinds = {c["kind"]: c for c in neighbors["candidates"]}
    # Before the first chosen photo: Kotor; after the last one: the clip has no location, so
    # the photo at 11:00 in Budva.
    assert (kinds["before"]["latitude"], kinds["before"]["longitude"]) == (
        KOTOR["latitude"],
        KOTOR["longitude"],
    )
    assert kinds["after"]["evidence"]["neighbors"][0]["delta_s"] == 45 * 60
    chosen = set(ids(photos, "a", "b", "located", "near"))
    assert not chosen & {p["asset_id"] for p in neighbors["track"]}


def test_no_located_photo_among_the_chosen(
    signed_in: TestClient, photos: dict[str, tuple[str, str]]
) -> None:
    found = blocks(signed_in, ids(photos, "a", "b"))
    assert found["selection"]["candidates"] == []
    assert found["selection"]["note"] == "none_located"


def test_confident_module_results_of_several_photos_as_one(
    signed_in: TestClient, photos: dict[str, tuple[str, str]]
) -> None:
    worker = start_worker(signed_in)
    for name in ("a", "b"):
        signed_in.post(f"/api/assets/{photos[name][0]}/modules/geoclip/run")
    place = {"radius_m": 5000.0, "kind": "area", "evidence": {}}
    confident = [{**KOTOR, "score": 0.9, **place}, {**BUDVA, "score": 0.3, **place}]
    finish(signed_in, worker, confident)
    finish(signed_in, worker, [{**KOTOR, "score": 0.8, **place}])

    geoclip = blocks(signed_in, ids(photos, "a", "b"))["geoclip"]
    [kotor] = geoclip["candidates"]
    assert kotor["evidence"]["photos"] == 2
    assert kotor["score"] == 0.9
    assert kotor["tier"] == "confident"
