# SPDX-License-Identifier: AGPL-3.0-or-later
"""M3 suggestions: similar photos with a location, searched when the suggestions are shown."""

import math
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text
from test_embeddings import encoded, run_module, start_worker

from steward.models import EMBEDDING_DIM, Account, Asset, Embedding, ModuleRun
from steward.modules.similar import CALIBRATION, calibrated

KOTOR = {"latitude": 42.4247, "longitude": 18.7712}
# About 300 m from Kotor.
KOTOR_NEAR = {"latitude": 42.4274, "longitude": 18.7712}
BUDVA = {"latitude": 42.2864, "longitude": 18.84}
ROME = {"latitude": 41.9, "longitude": 12.5}
PARIS = {"latitude": 48.86, "longitude": 2.35}
LEFT_HALF = {"x": 0.0, "y": 0.0, "w": 0.5, "h": 1.0}
# The vector of the photo the suggestions are for: the first axis.
QUERY = [1.0] + [0.0] * (EMBEDDING_DIM - 1)


def similar_to_query(similarity: float, index: int) -> list[float]:
    """A unit vector with this cosine similarity to the query vector (the first axis)."""
    values = [0.0] * EMBEDDING_DIM
    values[0] = similarity
    values[index] = math.sqrt(1 - similarity**2)
    return values


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    """File name -> local id; every photo has its vector."""
    photos = {
        "query.jpg": ({}, 1.0),
        "kotor.jpg": (KOTOR, 0.6),
        "kotor-near.jpg": (KOTOR_NEAR, 0.5),
        "budva.jpg": (BUDVA, 0.3),
        "paris.jpg": (PARIS, 0.05),  # too little alike: no suggestion
        "set-by-app.jpg": ({}, 0.7),
    }
    for hour, (file_name, (exif, _)) in enumerate(photos.items()):
        fake_immich.add_asset(
            taken=f"2024-05-01T{10 + hour}:00:00", originalFileName=file_name, exif=exif
        )
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    ids = {item["file_name"]: item["id"] for item in items}
    worker = start_worker(signed_in)
    for index, (file_name, (_, similarity)) in enumerate(photos.items(), start=1):
        vector = QUERY if file_name == "query.jpg" else similar_to_query(similarity, index)
        assert run_module(
            signed_in, worker, ids[file_name], {"embedding": encoded(vector)}
        ).is_success
    # A location set in the app: searched among by default (D-106).
    assert signed_in.put(f"/api/assets/{ids['set-by-app.jpg']}/location", json=ROME).is_success
    return ids


def similar(client: TestClient, asset_id: str, key: str = "similar") -> dict[str, Any]:
    response = client.get(f"/api/assets/{asset_id}/suggestions")
    assert response.status_code == 200
    module: dict[str, Any] = next(m for m in response.json() if m["key"] == key)
    return module


def evidence_files(candidate: dict[str, Any]) -> list[str]:
    return [n["file_name"] for n in candidate["evidence"]["neighbors"]]


def test_similar_photos_grouped_by_place(signed_in: TestClient, library: dict[str, str]) -> None:
    module = similar(signed_in, library["query.jpg"])
    assert (module["status"], module["shape"]) == ("done", "diamond")
    found = [(c["rank"], evidence_files(c), c["tier"], c["latitude"]) for c in module["candidates"]]
    assert found == [
        (1, ["set-by-app.jpg"], "confident", ROME["latitude"]),
        # Two photos 300 m apart are one place, at the spot of the more similar one.
        (2, ["kotor.jpg", "kotor-near.jpg"], "confident", KOTOR["latitude"]),
        (3, ["budva.jpg"], "normal", BUDVA["latitude"]),
    ]
    rome, kotor, _ = module["candidates"]
    assert kotor["score"] == pytest.approx(calibrated(0.6), abs=0.01)
    assert 250 <= kotor["radius_m"] <= 350
    first = kotor["evidence"]["neighbors"][0]
    assert first["similarity"] == pytest.approx(0.6, abs=0.002)
    assert first["estimated"] is False
    assert first["delta_s"] == 3600
    assert rome["evidence"]["neighbors"][0]["estimated"] is True


def test_locations_set_in_the_app_can_be_left_out(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    signed_in.app.state.settings.similar_include_estimated = False  # type: ignore[attr-defined]
    files = [evidence_files(c)[0] for c in similar(signed_in, library["query.jpg"])["candidates"]]
    assert files == ["kotor.jpg", "budva.jpg"]


def test_display_thresholds_are_settings(signed_in: TestClient, library: dict[str, str]) -> None:
    signed_in.app.state.settings.similar_min_confidence = 0.05  # type: ignore[attr-defined]
    candidates = similar(signed_in, library["query.jpg"])["candidates"]
    assert evidence_files(candidates[-1]) == ["paris.jpg"]
    assert candidates[-1]["tier"] == "weak"


def test_a_photo_never_suggests_itself_and_a_part_is_searched_too(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    worker = start_worker(signed_in)
    kotor = library["kotor.jpg"]
    run_module(signed_in, worker, kotor, {"embedding": encoded(QUERY)}, region=LEFT_HALF)
    part = similar(signed_in, kotor, key="similar:region")
    files = [f for c in part["candidates"] for f in evidence_files(c)]
    assert "kotor.jpg" not in files
    assert files[:2] == ["set-by-app.jpg", "kotor-near.jpg"]


def test_only_the_users_own_photos_are_searched(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    async def add_foreign_photo() -> None:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            account = Account(
                immich_user_id=uuid.uuid4(), name="Other", email="o@x", api_key_encrypted="x"
            )
            db.add(account)
            await db.flush()
            now = datetime.now(UTC)
            asset = Asset(
                account_id=account.id,
                immich_id=uuid.uuid4(),
                type="IMAGE",
                visibility="timeline",
                original_file_name="foreign.jpg",
                file_created_at=now,
                local_taken_at=now.replace(tzinfo=None),
                latitude=PARIS["latitude"],
                longitude=PARIS["longitude"],
                immich_updated_at=now,
                synced_at=now,
            )
            db.add(asset)
            await db.flush()
            run = ModuleRun(asset_id=asset.id, module_id="similar", status="done")
            db.add(run)
            await db.flush()
            db.add(
                Embedding(
                    run_id=run.id,
                    asset_id=asset.id,
                    account_id=account.id,
                    module_id="similar",
                    module_version="1",
                    region=False,
                    located=True,
                    vector=QUERY,
                )
            )
            await db.commit()

    signed_in.portal.call(add_foreign_photo)  # type: ignore[union-attr]
    files = [
        f for c in similar(signed_in, library["query.jpg"])["candidates"] for f in evidence_files(c)
    ]
    assert "foreign.jpg" not in files


def test_search_uses_the_index(signed_in: TestClient, library: dict[str, str]) -> None:
    """The query matches the partial HNSW index (D-108); without it the search scans everything."""

    async def plan() -> str:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            await db.execute(text("SET LOCAL enable_seqscan = off"))
            rows = await db.execute(
                text(
                    "EXPLAIN SELECT asset_id FROM embedding WHERE located "
                    "AND account_id = gen_random_uuid() AND module_id = 'similar' "
                    f"ORDER BY binary_quantize(vector)::bit({EMBEDDING_DIM}) <~> "
                    f"binary_quantize(CAST(:query AS halfvec({EMBEDDING_DIM}))) LIMIT 400"
                ).bindparams(bindparam("query", type_=Embedding.vector.type)),
                {"query": QUERY},
            )
            return "\n".join(row[0] for row in rows)

    assert "ix_embedding_search" in signed_in.portal.call(plan)  # type: ignore[union-attr]


def test_calibration_is_monotonic_and_bounded() -> None:
    scores = [calibrated(s / 100) for s in range(0, 101)]
    assert scores == sorted(scores)
    assert scores[0] == CALIBRATION[0][1]
    assert scores[-1] == CALIBRATION[-1][1]
    assert calibrated(0.22) == pytest.approx(0.55)
