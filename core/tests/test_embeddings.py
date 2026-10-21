# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vectors of the similar-photos module (M3): taken from workers, kept in step with locations."""

import base64
import struct
from typing import Any

import pytest
from conftest import WORKER_TOKEN, FakeImmich, sync
from fastapi.testclient import TestClient
from sqlalchemy import select

from steward import locations
from steward.api.worker import PROTOCOL_VERSION
from steward.models import EMBEDDING_DIM, Asset, Embedding

AUTH = {"Authorization": f"Bearer {WORKER_TOKEN}"}
GPS = {"latitude": 42.4, "longitude": 19.26}
KOTOR = {"latitude": 42.4247, "longitude": 18.7712}
LEFT_HALF = {"x": 0.0, "y": 0.0, "w": 0.5, "h": 1.0}


@pytest.fixture(autouse=True)
def fast_clear_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locations, "CLEAR_POLL_S", 0.0)


@pytest.fixture
def photos(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, tuple[str, str]]:
    """Name -> (local id, Immich id)."""
    immich_ids = {
        "todo": fake_immich.add_asset(taken="2024-05-01T10:00:00"),
        "gps": fake_immich.add_asset(taken="2024-05-01T11:00:00", exif=GPS),
    }
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    by_name = {item["file_name"]: item["id"] for item in items}
    return {
        name: (by_name[fake_immich.assets[immich_id]["originalFileName"]], immich_id)
        for name, immich_id in immich_ids.items()
    }


def encoded(values: list[float]) -> dict[str, Any]:
    data = struct.pack(f"<{len(values)}e", *values)
    return {"dim": len(values), "data": base64.b64encode(data).decode()}


def unit(index: int = 0) -> list[float]:
    values = [0.0] * EMBEDDING_DIM
    values[index] = 1.0
    return values


def start_worker(client: TestClient, modules: list[str] | None = None) -> dict[str, str]:
    body = {
        "name": "w",
        "modules": modules or ["similar"],
        "device": "cpu",
        "version": "0.3.0",
        "protocol_version": PROTOCOL_VERSION,
    }
    worker_id = client.post("/api/worker/register", json=body, headers=AUTH).json()["worker_id"]
    return AUTH | {"X-Worker-Id": worker_id}


def run_module(
    client: TestClient,
    worker: dict[str, str],
    asset: str,
    result: dict[str, Any],
    module: str = "similar",
    region: dict[str, float] | None = None,
) -> Any:
    client.post(
        f"/api/assets/{asset}/modules/{module}/run", json={"region": region} if region else None
    )
    job = client.post("/api/worker/lease", json={"modules": [module]}, headers=worker).json()
    body = {"module_version": "1", "candidates": []} | result
    return client.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)


def vectors(client: TestClient) -> list[tuple[str, bool, bool, float]]:
    """(file name, region, located, first number) of every stored vector."""

    async def work() -> list[tuple[str, bool, bool, float]]:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            rows = await db.execute(
                select(Asset.original_file_name, Embedding).join(
                    Asset, Asset.id == Embedding.asset_id
                )
            )
            return sorted((name, e.region, e.located, float(e.vector[0])) for name, e in rows)

    result: list[tuple[str, bool, bool, float]] = client.portal.call(work)  # type: ignore[union-attr]
    return result


def name(fake_immich: FakeImmich, immich_id: str) -> str:
    return str(fake_immich.assets[immich_id]["originalFileName"])


def test_one_vector_per_photo_and_part(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    worker = start_worker(signed_in)
    todo, gps = photos["todo"], photos["gps"]
    assert run_module(signed_in, worker, gps[0], {"embedding": encoded(unit())}).status_code == 204
    run_module(signed_in, worker, todo[0], {"embedding": encoded(unit())})
    run_module(signed_in, worker, todo[0], {"embedding": encoded(unit(1))}, region=LEFT_HALF)
    # Running again replaces the older vector of the photo.
    run_module(signed_in, worker, todo[0], {"embedding": encoded([0.5, *unit()[1:]])})

    assert vectors(signed_in) == sorted(
        [
            (name(fake_immich, gps[1]), False, True, 1.0),
            (name(fake_immich, todo[1]), False, False, 0.5),
            (name(fake_immich, todo[1]), True, False, 0.0),
        ]
    )
    block = next(
        m
        for m in signed_in.get(f"/api/assets/{todo[0]}/suggestions").json()
        if m["module"] == "similar"
    )
    assert block["status"] == "done"


@pytest.mark.parametrize(
    "result",
    [
        {},  # no vector at all
        {"embedding": encoded([1.0, 0.0])},  # wrong length
        {"embedding": {"dim": EMBEDDING_DIM, "data": "not base64!"}},
        {"embedding": {"dim": EMBEDDING_DIM, "data": base64.b64encode(b"\0" * 10).decode()}},
        {"embedding": encoded([float("inf"), *unit()[1:]])},
    ],
)
def test_invalid_vectors_are_refused(
    signed_in: TestClient, photos: dict[str, tuple[str, str]], result: dict[str, Any]
) -> None:
    worker = start_worker(signed_in)
    response = run_module(signed_in, worker, photos["todo"][0], result)
    assert (response.status_code, response.json()["code"]) == (422, "embedding_invalid")
    assert vectors(signed_in) == []


def test_modules_without_vectors_must_not_send_one(
    signed_in: TestClient, photos: dict[str, tuple[str, str]]
) -> None:
    worker = start_worker(signed_in, ["geoclip"])
    response = run_module(
        signed_in, worker, photos["todo"][0], {"embedding": encoded(unit())}, module="geoclip"
    )
    assert response.json()["code"] == "embedding_invalid"


def test_located_follows_the_location_of_the_photo(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    worker = start_worker(signed_in)
    (todo, todo_immich), (gps, gps_immich) = photos["todo"], photos["gps"]
    for asset in (todo, gps):
        run_module(signed_in, worker, asset, {"embedding": encoded(unit())})

    def located() -> dict[str, bool]:
        return {file: flag for file, _, flag, _ in vectors(signed_in)}

    todo_name, gps_name = name(fake_immich, todo_immich), name(fake_immich, gps_immich)
    assert located() == {todo_name: False, gps_name: True}

    # A location written by the app, and undone.
    assert signed_in.put(f"/api/assets/{todo}/location", json=KOTOR).status_code == 200
    assert located()[todo_name] is True
    assert signed_in.post(f"/api/assets/{todo}/location/undo").status_code == 200
    assert located()[todo_name] is False

    # Locations changed in Immich arrive with a sync.
    fake_immich.assets[gps_immich]["exifInfo"] |= {"latitude": None, "longitude": None}
    fake_immich.assets[todo_immich]["exifInfo"] |= GPS
    sync(signed_in, full=True)
    assert located() == {todo_name: True, gps_name: False}
