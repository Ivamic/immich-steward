# SPDX-License-Identifier: AGPL-3.0-or-later
"""Syncing the photos of the Immich locked folder (D-216, D-220)."""

from typing import Any

from conftest import FakeImmich, run_jobs, sync
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_locked_open import connected, open_with
from test_password_login import run_db

from steward.models import Asset


def visibilities(client: TestClient) -> dict[str, str]:
    rows = run_db(client, select(Asset.immich_id, Asset.visibility)).all()
    return {str(immich_id): visibility for immich_id, visibility in rows}


def keep_open(client: TestClient) -> Any:
    runner = client.app.state.job_runner  # type: ignore[attr-defined]
    runner._keep_open_at = 0.0
    return client.portal.call(runner.close_idle_locked)  # type: ignore[union-attr]


def test_open_folder_syncs_the_locked_photos(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    shown = fake_immich.add_asset()
    hidden = fake_immich.add_asset(visibility="locked")
    sync(signed_in, full=True)
    assert visibilities(signed_in) == {shown: "timeline"}

    connected(signed_in, fake_immich)
    open_with(signed_in, "123456")  # queues a sync
    run_jobs(signed_in)
    assert visibilities(signed_in) == {shown: "timeline", hidden: "locked"}
    # The API key never asked for the locked photos; the session asked only for them.
    assert all(body.get("visibility") != "locked" for body in fake_immich.search_requests[:3])


def test_closed_folder_keeps_its_photos_and_hides_the_moved_ones(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    moved = fake_immich.add_asset()
    hidden = fake_immich.add_asset(visibility="locked")
    connected(signed_in, fake_immich)
    open_with(signed_in, "123456")
    run_jobs(signed_in)
    signed_in.post("/api/locked/close")

    # Moved into the folder in Immich while it is closed here.
    fake_immich.assets[moved]["visibility"] = "locked"
    fake_immich.assets[moved]["updatedAt"] = "2026-06-01T00:00:00Z"
    sync(signed_in, full=True)
    assert visibilities(signed_in) == {moved: "missing", hidden: "locked"}

    # Opened again: the moved photo turns out locked, a deleted one goes.
    del fake_immich.assets[hidden]
    open_with(signed_in, "123456")
    run_jobs(signed_in)
    assert visibilities(signed_in) == {moved: "locked"}


def test_a_photo_deleted_while_closed_goes_at_the_next_opening(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    gone = fake_immich.add_asset()
    connected(signed_in, fake_immich)
    sync(signed_in, full=True)
    del fake_immich.assets[gone]
    sync(signed_in, full=True)
    assert visibilities(signed_in) == {gone: "missing"}
    open_with(signed_in, "123456")
    run_jobs(signed_in)
    assert visibilities(signed_in) == {}


def test_without_the_folder_nothing_changes(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    moved = fake_immich.add_asset()
    sync(signed_in, full=True)
    fake_immich.assets[moved]["visibility"] = "locked"
    sync(signed_in, full=True)
    assert visibilities(signed_in) == {}
    assert fake_immich.session_requests == []


def test_disconnecting_forgets_the_locked_photos(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    shown = fake_immich.add_asset()
    fake_immich.add_asset(visibility="locked")
    connected(signed_in, fake_immich)
    open_with(signed_in, "123456")
    run_jobs(signed_in)
    signed_in.delete("/api/locked")
    assert visibilities(signed_in) == {shown: "timeline"}


def test_a_folder_immich_closed_is_closed_here_and_the_sync_goes_on(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    shown = fake_immich.add_asset()
    fake_immich.add_asset(visibility="locked")
    connected(signed_in, fake_immich)
    open_with(signed_in, "123456")
    fake_immich.elevated.clear()  # 15 minutes passed in Immich without the session being used
    run_jobs(signed_in)
    assert visibilities(signed_in) == {shown: "timeline"}
    assert signed_in.get("/api/locked").json()["open"] is False


def test_the_app_keeps_the_folder_open_in_immich(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    connected(signed_in, fake_immich)
    keep_open(signed_in)
    assert "/api/auth/status" not in fake_immich.session_requests[2:]  # closed: nothing asked
    open_with(signed_in, "123456")
    asked = len(fake_immich.session_requests)
    keep_open(signed_in)
    assert fake_immich.session_requests[asked:] == ["/api/auth/status"]
    assert signed_in.get("/api/locked").json()["open"] is True
