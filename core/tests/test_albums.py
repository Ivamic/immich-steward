# SPDX-License-Identifier: AGPL-3.0-or-later
"""Changing albums in Immich from the app (D-233)."""

import uuid
from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient
from sqlalchemy import update

from steward.immich.compat import ALBUM_PERMISSIONS, REQUIRED_PERMISSIONS
from steward.models import Asset

ALL_ALBUM = sorted(REQUIRED_PERMISSIONS | set(ALBUM_PERMISSIONS.values()))


@pytest.fixture
def photos(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, tuple[str, str]]:
    """Name -> (local id, Immich id)."""
    fake_immich.permissions = ALL_ALBUM
    immich_ids = {
        "a": fake_immich.add_asset(taken="2024-05-01T10:00:00"),
        "b": fake_immich.add_asset(taken="2024-05-01T10:05:00"),
        "clip": fake_immich.add_asset(taken="2024-05-01T10:10:00", type="VIDEO"),
    }
    fake_immich.add_album("Trip", [immich_ids["a"]])
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    by_name = {item["file_name"]: item["id"] for item in items}
    return {
        name: (by_name[fake_immich.assets[immich_id]["originalFileName"]], immich_id)
        for name, immich_id in immich_ids.items()
    }


def album_list(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/albums")
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


def album(client: TestClient, name: str) -> dict[str, Any]:
    return next(a for a in album_list(client)["albums"] if a["name"] == name)


def in_album(client: TestClient, album_id: str) -> set[str]:
    items = client.get("/api/assets", params={"month": "2024-05", "album": album_id}).json()
    return {item["id"] for item in items}


def test_list_shows_role_cover_and_what_the_key_allows(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    other = {"user": {"id": str(uuid.uuid4())}, "role": "owner"}
    me = str(fake_immich.user_id)
    fake_immich.add_album(
        "Shared, editor",
        [],
        shared=True,
        albumUsers=[other, {"user": {"id": me}, "role": "editor"}],
    )
    fake_immich.add_album(
        "Shared, viewer",
        [],
        shared=True,
        albumUsers=[other, {"user": {"id": me}, "role": "viewer"}],
        startDate="2024-05-01T10:00:00Z",
    )
    sync(signed_in)

    listing = album_list(signed_in)
    assert [a["name"] for a in listing["albums"]] == ["Shared, editor", "Shared, viewer", "Trip"]
    assert listing["allowed"] == dict.fromkeys(ALBUM_PERMISSIONS, True)
    assert listing["immich_url"]
    trip, editor, viewer = (
        album(signed_in, n) for n in ("Trip", "Shared, editor", "Shared, viewer")
    )
    assert (trip["owned"], trip["can_change_photos"], trip["has_cover"]) == (True, True, True)
    assert trip["own_count"] == 1
    assert (editor["owned"], editor["can_change_photos"]) == (False, True)
    assert (viewer["owned"], viewer["can_change_photos"]) == (False, False)
    assert viewer["start_date"].startswith("2024-05-01")

    cover = signed_in.get(f"/api/albums/{trip['id']}/cover")
    assert cover.status_code == 200
    assert cover.content == f"image:{photos['a'][1]}:thumbnail".encode()

    fake_immich.permissions = sorted(REQUIRED_PERMISSIONS)
    assert not any(album_list(signed_in)["allowed"].values())


def test_add_reports_new_and_already_there_and_undo_removes_only_new(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    trip = album(signed_in, "Trip")
    ids = [photos[n][0] for n in ("a", "b", "clip")]

    added = signed_in.put(f"/api/albums/{trip['id']}/assets", json={"ids": ids}).json()

    assert sorted(added["added"]) == sorted([photos["b"][0], photos["clip"][0]])
    assert (added["already"], added["skipped_locked"], added["failed"]) == (1, 0, 0)
    assert added["created"] is False
    assert added["album"]["count"] == 3
    assert in_album(signed_in, trip["id"]) == set(ids)
    assert sorted(fake_immich.album_assets[trip["immich_id"]]) == sorted(
        p[1] for p in photos.values()
    )

    undo = signed_in.post(
        f"/api/albums/{trip['id']}/assets/remove", json={"ids": added["added"]}
    ).json()

    assert (undo["removed"], undo["failed"]) == (2, 0)
    assert sorted(undo["removed_ids"]) == sorted(added["added"])
    assert undo["album"]["own_count"] == 1
    assert fake_immich.album_assets[trip["immich_id"]] == [photos["a"][1]]
    assert in_album(signed_in, trip["id"]) == {photos["a"][0]}


def test_photos_of_the_locked_folder_are_left_out(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    async def lock() -> None:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            await db.execute(
                update(Asset).where(Asset.id == photos["b"][0]).values(visibility="locked")
            )
            await db.commit()

    signed_in.portal.call(lock)  # type: ignore[union-attr]
    trip = album(signed_in, "Trip")

    added = signed_in.put(
        f"/api/albums/{trip['id']}/assets", json={"ids": [photos["b"][0], photos["clip"][0]]}
    ).json()

    assert added["added"] == [photos["clip"][0]]
    assert added["skipped_locked"] == 1
    assert photos["b"][1] not in fake_immich.album_assets[trip["immich_id"]]


def test_create_with_photos_and_undo_by_deleting_it(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    created = signed_in.post(
        "/api/albums", json={"name": "  Videos 2024 ", "ids": [photos["clip"][0]]}
    ).json()

    assert created["created"] is True
    assert created["added"] == [photos["clip"][0]]
    new = created["album"]
    assert (new["name"], new["owned"], new["own_count"]) == ("Videos 2024", True, 1)
    assert fake_immich.album_assets[new["immich_id"]] == [photos["clip"][1]]
    assert in_album(signed_in, new["id"]) == {photos["clip"][0]}

    assert signed_in.delete(f"/api/albums/{new['id']}").status_code == 204

    assert new["immich_id"] not in fake_immich.albums
    assert photos["clip"][1] in fake_immich.assets  # the photo stays
    assert [a["name"] for a in album_list(signed_in)["albums"]] == ["Trip"]


def test_create_empty_and_rename(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    new = signed_in.post("/api/albums", json={"name": "Later"}).json()["album"]
    assert new["count"] == 0

    renamed = signed_in.patch(f"/api/albums/{new['id']}", json={"name": "Sooner"})

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Sooner"
    assert fake_immich.albums[new["immich_id"]]["albumName"] == "Sooner"
    assert signed_in.patch(f"/api/albums/{new['id']}", json={"name": "  "}).status_code == 422


def test_shared_album_of_someone_else(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    other = {"user": {"id": str(uuid.uuid4())}, "role": "owner"}
    me = str(fake_immich.user_id)
    fake_immich.add_album(
        "Theirs", [], shared=True, albumUsers=[other, {"user": {"id": me}, "role": "viewer"}]
    )
    sync(signed_in)
    theirs = album(signed_in, "Theirs")
    changes = fake_immich.album_changes

    add = signed_in.put(f"/api/albums/{theirs['id']}/assets", json={"ids": [photos["a"][0]]})
    rename = signed_in.patch(f"/api/albums/{theirs['id']}", json={"name": "Mine"})
    delete = signed_in.delete(f"/api/albums/{theirs['id']}")

    assert (add.status_code, add.json()["code"]) == (403, "album_read_only")
    assert (rename.status_code, rename.json()["code"]) == (403, "album_not_owned")
    assert (delete.status_code, delete.json()["code"]) == (403, "album_not_owned")
    assert fake_immich.album_changes == changes  # nothing was asked of Immich


def test_missing_permission_is_named(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    fake_immich.permissions = sorted(REQUIRED_PERMISSIONS)
    trip = album(signed_in, "Trip")

    response = signed_in.put(f"/api/albums/{trip['id']}/assets", json={"ids": [photos["b"][0]]})

    assert response.status_code == 403
    assert response.json() == {
        "code": "immich_missing_permissions",
        "params": {"permissions": ["albumAsset.create"]},
    }
    assert in_album(signed_in, trip["id"]) == {photos["a"][0]}


def test_unknown_album_and_other_accounts_photos(
    signed_in: TestClient, photos: dict[str, tuple[str, str]]
) -> None:
    trip = album(signed_in, "Trip")
    missing = signed_in.put(f"/api/albums/{uuid.uuid4()}/assets", json={"ids": [photos["a"][0]]})
    assert missing.status_code == 404

    stranger = signed_in.put(f"/api/albums/{trip['id']}/assets", json={"ids": [str(uuid.uuid4())]})
    assert stranger.json()["added"] == []


def test_photo_card_tells_which_albums_it_can_leave(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    other = {"user": {"id": str(uuid.uuid4())}, "role": "owner"}
    me = str(fake_immich.user_id)
    fake_immich.add_album(
        "Theirs",
        [photos["a"][1]],
        shared=True,
        albumUsers=[other, {"user": {"id": me}, "role": "viewer"}],
    )
    sync(signed_in)

    detail = signed_in.get(f"/api/assets/{photos['a'][0]}").json()

    assert [(a["name"], a["can_change_photos"]) for a in detail["albums"]] == [
        ("Theirs", False),
        ("Trip", True),
    ]


def test_which_albums_have_the_photos_already(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    trip = album(signed_in, "Trip")
    ids = [photos[n][0] for n in ("a", "b", "clip")]

    counts = signed_in.post("/api/albums/contains", json={"ids": ids}).json()["counts"]

    assert counts == {trip["id"]: 1}
    other = signed_in.post("/api/albums/contains", json={"ids": [photos["b"][0]]}).json()
    assert other["counts"] == {}


def test_an_album_just_changed_comes_first_among_the_recent(
    signed_in: TestClient, fake_immich: FakeImmich, photos: dict[str, tuple[str, str]]
) -> None:
    fake_immich.add_album("Newer", [], updatedAt="2026-06-01T00:00:00Z")
    sync(signed_in)
    trip = album(signed_in, "Trip")
    newer = album(signed_in, "Newer")
    assert trip["updated_at"] < newer["updated_at"]

    signed_in.put(f"/api/albums/{trip['id']}/assets", json={"ids": [photos["b"][0]]})

    assert album(signed_in, "Trip")["updated_at"] > newer["updated_at"]
