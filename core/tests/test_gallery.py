# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient

GPS = {"latitude": 42.4, "longitude": 19.26}


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    ids = {
        "may_gps": fake_immich.add_asset(taken="2024-05-03T12:00:00", exif=GPS),
        "may_late": fake_immich.add_asset(taken="2024-05-31T23:59:59"),
        "june": fake_immich.add_asset(taken="2024-06-01T00:00:00"),
        "june_video": fake_immich.add_asset(taken="2024-06-15T08:00:00", type="VIDEO"),
        "old_phone": fake_immich.add_asset(
            taken="2009-08-01T10:00:00", exif={"make": "SonyEricsson", "model": "K800i"}
        ),
        "archived": fake_immich.add_asset(taken="2024-06-20T10:00:00", visibility="archive"),
        "trashed": fake_immich.add_asset(taken="2024-06-21T10:00:00", isTrashed=True),
    }
    fake_immich.add_album("Summer", [ids["june"], ids["june_video"]])
    sync(signed_in)
    return ids


def months(client: TestClient, **params: Any) -> dict[str, int]:
    response = client.get("/api/assets/months", params=params)
    assert response.status_code == 200
    return {bucket["month"]: bucket["count"] for bucket in response.json()}


def month(client: TestClient, value: str, **params: Any) -> list[dict[str, Any]]:
    response = client.get("/api/assets", params={"month": value, **params})
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()
    return items


@pytest.mark.usefixtures("library")
def test_month_buckets_and_filters(signed_in: TestClient) -> None:
    # Newest first; archived and trashed assets are hidden by default.
    assert list(months(signed_in).items()) == [("2024-06", 2), ("2024-05", 2), ("2009-08", 1)]
    assert months(signed_in, archived=True)["2024-06"] == 3
    assert months(signed_in, show="with") == {"2024-05": 1}
    assert sum(months(signed_in, show="todo").values()) == 4
    assert sum(months(signed_in, show=["todo", "with"]).values()) == 5
    assert months(signed_in, type="video") == {"2024-06": 1}
    assert months(signed_in, date_from="2024-05-31", date_to="2024-06-01") == {
        "2024-06": 1,
        "2024-05": 1,
    }


@pytest.mark.usefixtures("library")
def test_months_count_their_days(signed_in: TestClient) -> None:
    buckets = signed_in.get("/api/assets/months").json()
    # May has a photo on the 31st and one on the 3rd: two days, newest first.
    assert {b["month"]: b["days"] for b in buckets}["2024-05"] == [1, 1]
    assert all(sum(b["days"]) == b["count"] for b in buckets)


@pytest.mark.usefixtures("library")
def test_month_items_are_bounded_by_local_time(signed_in: TestClient) -> None:
    may = month(signed_in, "2024-05")
    assert [item["local_taken_at"] for item in may] == [
        "2024-05-31T23:59:59",
        "2024-05-03T12:00:00",
    ]
    assert [item["has_location"] for item in may] == [False, True]
    assert signed_in.get("/api/assets", params={"month": "2024-13"}).status_code == 422


@pytest.mark.usefixtures("library")
def test_filter_options_and_camera_album_filters(signed_in: TestClient) -> None:
    options = signed_in.get("/api/assets/filter-options").json()
    cameras = {c["model"]: c for c in options["cameras"]}
    assert cameras["EOS 300D"]["count"] == 5  # archived assets count, trashed do not
    assert options["albums"][0]["name"] == "Summer"
    assert options["albums"][0]["count"] == 2
    assert set(options["failed_modules"]) == {"geoclip", "similar"}

    assert months(signed_in, camera=cameras["K800i"]["value"]) == {"2009-08": 1}
    assert months(signed_in, album=options["albums"][0]["id"]) == {"2024-06": 2}


def test_fullsize_falls_back_to_preview_without_download_permission(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    asset_id = month(signed_in, "2024-05")[0]["id"]
    url = f"/api/assets/{asset_id}/thumbnail"
    response = signed_in.get(url, params={"size": "fullsize"})
    assert response.status_code == 200
    assert response.content.endswith(b":preview")

    fake_immich.permissions.append("asset.download")
    response = signed_in.get(url, params={"size": "fullsize"}, headers={"if-none-match": "x"})
    assert response.content == b"original"


def test_thumbnail_proxy_with_etag(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    asset_id = month(signed_in, "2024-05")[1]["id"]
    response = signed_in.get(f"/api/assets/{asset_id}/thumbnail", params={"size": "preview"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.content == f"image:{library['may_gps']}:preview".encode()
    assert "private" in response.headers["cache-control"]

    cached = signed_in.get(
        f"/api/assets/{asset_id}/thumbnail",
        params={"size": "preview"},
        headers={"if-none-match": response.headers["etag"]},
    )
    assert cached.status_code == 304
    assert fake_immich.thumbnail_requests == 1


def test_other_accounts_assets_are_invisible(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    asset_id = month(signed_in, "2024-05")[0]["id"]
    signed_in.post("/api/auth/logout")
    other = FakeImmich()
    fake_immich.user_id = other.user_id  # the same key now belongs to another Immich user
    assert signed_in.post("/api/auth/login", json={"api_key": "valid-key"}).status_code == 200

    assert months(signed_in) == {}
    assert signed_in.get(f"/api/assets/{asset_id}/thumbnail").status_code == 404


def asset_id_of(client: TestClient, month_value: str, index: int = 0) -> str:
    return str(month(client, month_value)[index]["id"])


@pytest.mark.usefixtures("library")
def test_detail_and_neighbors_follow_the_filter(signed_in: TestClient) -> None:
    newest_june = asset_id_of(signed_in, "2024-06")
    detail = signed_in.get(f"/api/assets/{newest_june}").json()
    assert detail["type"] == "VIDEO"
    assert detail["albums"] == ["Summer"]
    assert detail["review_status"] == "new"
    assert detail["previous_id"] is None  # newest photo of the library

    # Walk the whole gallery with "next": newest to oldest, archived and trashed excluded.
    seen, current = [], newest_june
    while current:
        seen.append(current)
        current = signed_in.get(f"/api/assets/{current}").json()["next_id"]
    assert len(seen) == 5

    # Under a filter, neighbors skip photos that do not match it.
    with_location = signed_in.get(f"/api/assets/{newest_june}", params={"show": "with"}).json()
    may_gps = signed_in.get(f"/api/assets/{with_location['next_id']}").json()
    assert may_gps["latitude"] == pytest.approx(42.4)


@pytest.mark.usefixtures("library")
def test_review_status_moves_photo_between_views(signed_in: TestClient) -> None:
    june = asset_id_of(signed_in, "2024-06", 1)
    todo_before = sum(months(signed_in, show="todo").values())

    response = signed_in.put(f"/api/assets/{june}/review", json={"status": "not_applicable"})
    assert response.json()["review_status"] == "not_applicable"
    assert sum(months(signed_in, show="todo").values()) == todo_before - 1
    assert months(signed_in, show="not_applicable") == {"2024-06": 1}

    signed_in.put(f"/api/assets/{june}/review", json={"status": "skipped"})
    assert months(signed_in, show="skipped") == {"2024-06": 1}
    assert months(signed_in, show="not_applicable") == {}

    signed_in.put(f"/api/assets/{june}/review", json={"status": "new"})
    assert sum(months(signed_in, show="todo").values()) == todo_before
    bad = signed_in.put(f"/api/assets/{june}/review", json={"status": "confirmed"})
    assert bad.status_code == 422


def test_review_status_survives_sync(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    june = asset_id_of(signed_in, "2024-06", 1)
    signed_in.put(f"/api/assets/{june}/review", json={"status": "skipped"})
    sync(signed_in, full=True)
    assert signed_in.get(f"/api/assets/{june}").json()["review_status"] == "skipped"
