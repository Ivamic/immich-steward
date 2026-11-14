# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where locked photos are shown: nowhere while the folder is closed; with their own filter while
it is open; as hint sources always, but without a name while closed (D-216)."""

import uuid
from typing import Any

from conftest import FakeImmich, run_jobs
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_locked_open import connected, open_with
from test_password_login import run_db

from steward.models import Asset

PLACE = {"latitude": 45.4642, "longitude": 9.19}


def months(client: TestClient, **params: Any) -> dict[str, int]:
    response = client.get("/api/assets/months", params=params)
    assert response.status_code == 200
    return {bucket["month"]: bucket["count"] for bucket in response.json()}


def library(client: TestClient, fake: FakeImmich) -> tuple[str, str]:
    """A photo in the timeline and a located one in the locked folder, taken 10 minutes apart;
    returns their Steward ids."""
    shown = fake.add_asset(taken="2024-05-01T10:10:00")
    hidden = fake.add_asset(taken="2024-05-01T10:00:00", visibility="locked", exif=PLACE)
    connected(client, fake)
    open_with(client, "123456")
    run_jobs(client)
    rows = dict(run_db(client, select(Asset.immich_id, Asset.id)).all())
    return str(rows[uuid.UUID(shown)]), str(rows[uuid.UUID(hidden)])


def test_the_gallery_shows_locked_photos_only_with_their_filter_while_open(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    _, hidden = library(signed_in, fake_immich)
    show_all = {"show": ["todo", "with", "skipped", "not_applicable"]}
    assert months(signed_in, **show_all) == {"2024-05": 1}
    assert months(signed_in, **show_all, locked_folder=True) == {"2024-05": 2}
    items = signed_in.get(
        "/api/assets", params={"month": "2024-05", **show_all, "locked_folder": True}
    ).json()
    assert [item["locked"] for item in items if item["id"] == hidden] == [True]

    assert months(signed_in, **show_all, locked_folder="only") == {"2024-05": 1}
    # The archive alone and the locked folder with it: both, without the timeline (none here).
    assert months(signed_in, **show_all, archived="only", locked_folder="with") == {"2024-05": 1}

    signed_in.post("/api/locked/close")
    assert months(signed_in, **show_all, locked_folder=True) == {"2024-05": 1}
    assert months(signed_in, **show_all, locked_folder="only") == {}


def test_counts_and_the_heat_map_leave_out_a_closed_folder(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    library(signed_in, fake_immich)
    assert signed_in.get("/api/library").json()["assets"] == 2
    assert len(signed_in.get("/api/assets/heatmap").json()) == 3
    signed_in.post("/api/locked/close")
    assert signed_in.get("/api/library").json()["assets"] == 1
    assert signed_in.get("/api/assets/heatmap").json() == []


def test_the_card_of_a_locked_photo_needs_the_folder_open(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    _, hidden = library(signed_in, fake_immich)
    response = signed_in.get(f"/api/assets/{hidden}")
    assert response.status_code == 200 and response.json()["locked"] is True
    signed_in.post("/api/locked/close")
    response = signed_in.get(f"/api/assets/{hidden}")
    assert response.status_code == 423
    assert response.json()["code"] == "locked_closed"


def test_a_missing_photo_is_never_reached(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    _, hidden = library(signed_in, fake_immich)
    run_db(signed_in, update(Asset).where(Asset.id == hidden).values(visibility="missing"))
    assert signed_in.get(f"/api/assets/{hidden}").status_code == 404


def test_a_locked_photo_helps_but_is_not_named_while_closed(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    shown, hidden = library(signed_in, fake_immich)

    def time_neighbors() -> dict[str, Any]:
        response = signed_in.get(f"/api/assets/{shown}/suggestions")
        assert response.status_code == 200
        block: dict[str, Any] = response.json()[0]
        assert block["module"] == "time_neighbors"
        return block

    opened = time_neighbors()
    [point] = opened["track"]
    assert point["asset_id"] == hidden and not point["locked"] and point["file_name"]

    signed_in.post("/api/locked/close")
    closed = time_neighbors()
    # The suggestion stays: the place is the user's own.
    assert closed["candidates"][0]["latitude"] == PLACE["latitude"]
    [point] = closed["track"]
    assert point["locked"] is True and point["file_name"] == ""
    [neighbor] = closed["candidates"][0]["evidence"]["neighbors"]
    assert neighbor["locked"] is True
    assert neighbor.get("file_name", "") == ""
