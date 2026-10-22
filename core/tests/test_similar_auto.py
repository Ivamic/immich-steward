# SPDX-License-Identifier: AGPL-3.0-or-later
"""Automatic runs of similar photos (M3) and photos whose image changed in Immich."""

from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_embeddings import encoded, run_module, start_worker, unit
from test_module_runs import schedule

from steward.models import Asset, Embedding, ModuleRun

GPS = {"latitude": 42.4, "longitude": 19.26}


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    """File name -> Immich id."""
    photos = {
        "todo.jpg": {},
        "gps.jpg": {"exif": GPS},
        "gps-archived.jpg": {"exif": GPS, "visibility": "archive"},
        "gps-video.mp4": {"exif": GPS, "type": "VIDEO"},
        "screenshot.png": {},
    }
    ids = {}
    for hour, (file_name, fields) in enumerate(photos.items()):
        ids[file_name] = fake_immich.add_asset(
            taken=f"2024-05-01T{10 + hour}:00:00",
            originalFileName=file_name,
            thumbhash="hash-1",
            **fields,
        )
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05", "archived": True}).json()
    local = {item["file_name"]: item["id"] for item in items}
    signed_in.put(
        f"/api/assets/{local['screenshot.png']}/review", json={"status": "not_applicable"}
    )
    return ids


def queued(client: TestClient, module: str) -> list[str]:
    """File names of the queued runs of the module, in the order workers take them."""
    names = []
    # Once: registering again would give the jobs it holds back to the queue.
    worker = start_worker(client, [module])
    while True:
        job = client.post("/api/worker/lease", json={"modules": [module]}, headers=worker)
        if job.status_code == 204:
            return names
        asset = client.get(f"/api/assets/{job.json()['asset_id']}").json()
        names.append(asset["file_name"])


def test_photos_with_a_location_are_indexed_first(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    start_worker(signed_in, ["similar", "geoclip"])
    schedule(signed_in)
    # The search index first (archived photos too), then the photos to do; never videos or
    # photos marked "not applicable".
    assert queued(signed_in, "similar") == ["gps-archived.jpg", "gps.jpg", "todo.jpg"]
    # GeoCLIP stays with the photos without a location.
    assert queued(signed_in, "geoclip") == ["todo.jpg"]


def test_index_progress(signed_in: TestClient, library: dict[str, str]) -> None:
    worker = start_worker(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    gps = next(item["id"] for item in items if item["file_name"] == "gps.jpg")
    run_module(signed_in, worker, gps, {"embedding": encoded(unit())})
    index = signed_in.get("/api/library/workers").json()["index"]
    assert index == {"similar": {"indexed": 1, "located": 2}}


def runs(client: TestClient) -> list[tuple[str, str]]:
    async def work() -> list[tuple[str, str]]:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            rows = await db.execute(
                select(Asset.original_file_name, ModuleRun.module_id).join(
                    Asset, Asset.id == ModuleRun.asset_id
                )
            )
            return sorted((name, module) for name, module in rows)

    result: list[tuple[str, str]] = client.portal.call(work)  # type: ignore[union-attr]
    return result


def vectors(client: TestClient) -> int:
    async def work() -> Any:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return len((await db.scalars(select(Embedding.run_id))).all())

    result: int = client.portal.call(work)  # type: ignore[union-attr]
    return result


def test_rotated_photo_is_run_again(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    local = {item["file_name"]: item["id"] for item in items}
    similar_worker = start_worker(signed_in, ["similar"])
    geoclip_worker = start_worker(signed_in, ["geoclip"])
    for name in ("todo.jpg", "gps.jpg"):
        run_module(signed_in, similar_worker, local[name], {"embedding": encoded(unit())})
    area = {"latitude": 41.9, "longitude": 12.5, "score": 0.8}
    run_module(signed_in, geoclip_worker, local["todo.jpg"], {"candidates": [area]}, "geoclip")
    run_module(
        signed_in,
        geoclip_worker,
        local["todo.jpg"],
        {"candidates": [area]},
        "geoclip",
        region={"x": 0.0, "y": 0.0, "w": 0.5, "h": 1.0},
    )
    before = runs(signed_in)
    assert ("todo.jpg", "geoclip") in before

    # Unchanged thumbnails: nothing happens.
    sync(signed_in, full=True)
    assert runs(signed_in) == before

    # The photo was rotated in Immich: its thumbnails are new. GeoCLIP, similar photos and the
    # run on a part all go; the other photo keeps its vector.
    fake_immich.assets[library["todo.jpg"]]["thumbhash"] = "hash-2"
    sync(signed_in, full=True)
    assert runs(signed_in) == [("gps.jpg", "similar")]
    assert vectors(signed_in) == 1
    # Automatic runs take the photo again.
    start_worker(signed_in, ["similar", "geoclip"])
    schedule(signed_in)
    assert "todo.jpg" in queued(signed_in, "geoclip")


def test_first_thumbhash_is_not_a_change(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    """Assets synced before the app knew thumbhashes keep their results."""
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    todo = next(item["id"] for item in items if item["file_name"] == "todo.jpg")

    async def forget_hashes() -> None:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            for asset in await db.scalars(select(Asset)):
                asset.thumbhash = None
            await db.commit()

    run_module(signed_in, start_worker(signed_in), todo, {"embedding": encoded(unit())})
    signed_in.portal.call(forget_hashes)  # type: ignore[union-attr]
    sync(signed_in, full=True)
    assert runs(signed_in) == [("todo.jpg", "similar")]
