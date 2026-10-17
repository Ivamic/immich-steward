# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from typing import Any

import pytest
from conftest import FakeImmich
from fastapi.testclient import TestClient
from sqlalchemy import select

from steward.models import Asset


@pytest.fixture
def signed_in(client: TestClient) -> TestClient:
    assert client.post("/api/auth/login", json={"api_key": "valid-key"}).status_code == 200
    return client


def run_jobs(client: TestClient) -> None:
    runner = client.app.state.job_runner  # type: ignore[attr-defined]
    while client.portal.call(runner.run_once):  # type: ignore[union-attr]
        pass


def sync(client: TestClient, full: bool | None = None) -> dict[str, Any]:
    job = client.post("/api/library/sync", json={"full": full})
    assert job.status_code == 202
    run_jobs(client)
    library: dict[str, Any] = client.get("/api/library").json()
    return library


def local_assets(client: TestClient) -> list[Asset]:
    async def query() -> list[Asset]:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return list(await db.scalars(select(Asset).order_by(Asset.original_file_name)))

    return client.portal.call(query)  # type: ignore[union-attr]


def test_full_sync(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    with_gps = fake_immich.add_asset(exif={"latitude": 42.4, "longitude": 19.26})
    no_gps = fake_immich.add_asset(taken="2024-05-01T10:05:00")
    fake_immich.add_asset(type="VIDEO")
    fake_immich.add_asset(visibility="archive")
    fake_immich.add_asset(isTrashed=True)
    fake_immich.add_asset(visibility="hidden")  # live photo video part: not synced
    fake_immich.add_asset(ownerId=str(uuid.uuid4()))  # someone else's asset: not synced
    fake_immich.add_album("Trip", [with_gps, no_gps])

    library = sync(signed_in)

    assert library["assets"] == 4  # trashed asset is stored but not counted
    assert library["videos"] == 1
    assert library["with_gps"] == 1
    assert library["without_gps"] == 3
    assert library["albums"] == 1
    assert library["synced_at"] == library["full_synced_at"]
    job = library["sync_job"]
    assert job["status"] == "done"
    assert job["progress"]["full"] is True
    assert len(local_assets(signed_in)) == 5

    # Wall-clock capture time is kept as is, without a time zone.
    stored = {a.immich_id: a for a in local_assets(signed_in)}
    assert stored[uuid.UUID(no_gps)].local_taken_at.isoformat() == "2024-05-01T10:05:00"


def test_incremental_sync_and_deletions(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    changed = fake_immich.add_asset()
    removed = fake_immich.add_asset()
    sync(signed_in)

    fake_immich.assets[changed]["exifInfo"] |= {"latitude": 1.0, "longitude": 2.0}
    fake_immich.assets[changed]["updatedAt"] = "2099-01-01T00:00:00Z"
    fake_immich.add_asset(updatedAt="2099-01-01T00:00:00Z")
    del fake_immich.assets[removed]
    fake_immich.search_requests.clear()

    library = sync(signed_in, full=False)
    assert library["sync_job"]["progress"] == {
        "full": False,
        "assets": 2,
        "removed": 0,
        "albums": 0,
    }
    assert library["with_gps"] == 1
    assert library["assets"] == 3  # the deleted asset is noticed only by a full sync
    assert all("updatedAfter" in body for body in fake_immich.search_requests)

    assert sync(signed_in, full=True)["assets"] == 2


def test_album_membership_follows_immich(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    first, second = fake_immich.add_asset(), fake_immich.add_asset()
    album = fake_immich.add_album("Trip", [first])
    sync(signed_in)

    fake_immich.album_assets[album] = [first, second]
    fake_immich.albums[album]["updatedAt"] = "2099-01-01T00:00:00Z"
    sync(signed_in, full=False)

    async def members() -> int:
        from sqlalchemy import func

        from steward.models import AssetAlbum

        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return int(await db.scalar(select(func.count()).select_from(AssetAlbum)) or 0)

    assert signed_in.portal.call(members) == 2  # type: ignore[union-attr]

    del fake_immich.albums[album]
    assert sync(signed_in)["albums"] == 0


def test_sync_request_is_not_duplicated(signed_in: TestClient) -> None:
    first = signed_in.post("/api/library/sync", json={}).json()
    second = signed_in.post("/api/library/sync", json={}).json()
    assert first["id"] == second["id"]
    assert first["status"] == "queued"


def test_sync_fails_cleanly_when_key_is_revoked(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    fake_immich.valid_key = "rotated"
    job = sync(signed_in)["sync_job"]
    assert job["status"] == "failed"
    assert job["error"] == "immich_invalid_api_key"


def test_scheduler_queues_sync_for_new_accounts(signed_in: TestClient) -> None:
    runner = signed_in.app.state.job_runner  # type: ignore[attr-defined]
    signed_in.portal.call(runner.schedule_syncs)  # type: ignore[union-attr]
    job = signed_in.get("/api/library").json()["sync_job"]
    assert job["status"] == "queued"


def test_library_requires_sign_in(client: TestClient) -> None:
    assert client.get("/api/library").status_code == 401
    assert client.post("/api/library/sync", json={}).status_code == 401
