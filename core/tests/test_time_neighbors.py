# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

import pytest
from conftest import FakeImmich, sync
from fastapi.testclient import TestClient

from steward.modules.time_neighbors import distance_m

A = {"latitude": 42.0, "longitude": 19.0}
B = {"latitude": 42.01, "longitude": 19.0}  # 1.1 km north of A
SCANNER = {"make": "EPSON", "model": "Perfection V600"}
PHONE = {"make": "Apple", "model": "iPhone 15 Pro Max"}


def add(fake: FakeImmich, taken: str, **exif: Any) -> str:
    return fake.add_asset(taken=f"2024-05-01T{taken}", exif=exif)


def local_id(client: TestClient, fake: FakeImmich, immich_id: str) -> str:
    name = fake.assets[immich_id]["originalFileName"]
    items = client.get("/api/assets", params={"month": "2024-05"}).json()
    return next(item["id"] for item in items if item["file_name"] == name)


def m1(client: TestClient, fake: FakeImmich, immich_id: str) -> dict[str, Any]:
    sync(client)
    response = client.get(f"/api/assets/{local_id(client, fake, immich_id)}/suggestions")
    assert response.status_code == 200
    return time_neighbors(response.json())


def time_neighbors(modules: list[dict[str, Any]]) -> dict[str, Any]:
    """The M1 block of a suggestions response (worker modules follow it)."""
    assert modules[0]["module"] == "time_neighbors"
    return modules[0]


def test_between_before_and_after(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    add(fake_immich, "10:00:00", **A)
    target = add(fake_immich, "10:10:00")
    add(fake_immich, "10:20:00", **B)
    result = m1(signed_in, fake_immich, target)

    kinds = [c["kind"] for c in result["candidates"]]
    assert kinds == ["between", "before", "after"]
    between = result["candidates"][0]
    assert between["rank"] == 1
    assert between["latitude"] == pytest.approx(42.005)
    assert between["evidence"]["share"] == pytest.approx(0.5)
    assert [n["delta_s"] for n in between["evidence"]["neighbors"]] == [-600, 600]
    assert result["candidates"][1]["radius_m"] == pytest.approx(650)
    assert [p["role"] for p in result["track"]] == ["before", "after"]


def test_only_one_side(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    add(fake_immich, "09:00:00", **A)
    target = add(fake_immich, "10:00:00")
    [candidate] = m1(signed_in, fake_immich, target)["candidates"]
    assert candidate["kind"] == "before"
    assert candidate["score"] == pytest.approx(0.368, abs=0.01)


def test_same_camera_is_preferred(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    add(fake_immich, "09:00:00", **A)  # same camera (Canon), an hour earlier
    add(fake_immich, "09:55:00", **B, **PHONE)  # another camera, 5 minutes earlier
    target = add(fake_immich, "10:00:00")
    result = m1(signed_in, fake_immich, target)
    before = next(p for p in result["track"] if p["role"] == "before")
    assert before["same_camera"] is True
    assert before["latitude"] == A["latitude"]
    assert [p["same_camera"] for p in result["track"]] == [True, False]


def test_other_camera_counts_with_lower_score(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    add(fake_immich, "09:55:00", **B, **PHONE)
    target = add(fake_immich, "10:00:00")
    [candidate] = m1(signed_in, fake_immich, target)["candidates"]
    assert candidate["score"] == pytest.approx(0.92 * 0.6, abs=0.01)


def test_neighbors_outside_the_window_are_ignored(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    add(fake_immich, "06:00:00", **A)
    target = add(fake_immich, "10:00:00")
    assert m1(signed_in, fake_immich, target)["note"] == "no_neighbors"

    signed_in.app.state.settings.time_neighbors_window_hours = 5  # type: ignore[attr-defined]
    assert len(m1(signed_in, fake_immich, target)["candidates"]) == 1


def test_scans_get_no_suggestions(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    add(fake_immich, "10:00:00", **A)
    target = add(fake_immich, "10:05:00", **SCANNER)
    result = m1(signed_in, fake_immich, target)
    assert result["note"] == "scanner"
    assert result["candidates"] == []


def test_no_interpolation_for_impossible_speed(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    add(fake_immich, "10:00:00", **A)
    target = add(fake_immich, "10:10:00")
    add(fake_immich, "10:20:00", latitude=50.0, longitude=19.0)  # 900 km in 20 minutes
    kinds = [c["kind"] for c in m1(signed_in, fake_immich, target)["candidates"]]
    assert sorted(kinds) == ["after", "before"]


def test_close_candidates_are_merged(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    add(fake_immich, "10:00:00", **A)
    target = add(fake_immich, "10:10:00")
    add(fake_immich, "10:30:00", latitude=42.0003, longitude=19.0)  # 33 m away
    # The interpolated point scores best and absorbs the two neighbors next to it.
    [candidate] = m1(signed_in, fake_immich, target)["candidates"]
    assert candidate["kind"] == "between"


def test_locations_written_by_the_app_are_marked(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    neighbor = add(fake_immich, "10:00:00")
    target = add(fake_immich, "10:10:00")
    sync(signed_in)
    signed_in.put(f"/api/assets/{local_id(signed_in, fake_immich, neighbor)}/location", json=A)
    [point] = m1(signed_in, fake_immich, target)["track"]
    assert point["estimated"] is True


def test_distance() -> None:
    assert distance_m(**{"lat1": 42.0, "lon1": 19.0, "lat2": 42.01, "lon2": 19.0}) == (
        pytest.approx(1112, abs=2)
    )


def test_cameras_are_listed_and_can_be_excluded(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    add(fake_immich, "09:00:00", **A)  # same camera, an hour earlier
    add(fake_immich, "09:55:00", **B, **PHONE)  # another camera, 5 minutes earlier
    add(fake_immich, "09:58:00", **B, **PHONE)
    target = add(fake_immich, "10:00:00")
    result = m1(signed_in, fake_immich, target)
    cameras = result["cameras"]
    assert [(c["label"], c["count"], c["same_camera"]) for c in cameras] == [
        ("Canon EOS 300D", 1, True),
        ("Apple iPhone 15 Pro Max", 2, False),
    ]
    assert result["track"][-1]["camera"] == "Apple iPhone 15 Pro Max"

    sync(signed_in)
    url = f"/api/assets/{local_id(signed_in, fake_immich, target)}/suggestions"
    without_phone = time_neighbors(
        signed_in.get(url, params={"exclude_camera": cameras[1]["value"]}).json()
    )
    assert [p["camera"] for p in without_phone["track"]] == ["Canon EOS 300D"]
    assert [c["excluded"] for c in without_phone["cameras"]] == [False, True]

    nothing = time_neighbors(
        signed_in.get(url, params={"exclude_camera": [c["value"] for c in cameras]}).json()
    )
    assert nothing["note"] == "no_neighbors"
    assert len(nothing["cameras"]) == 2


def test_only_this_camera(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    add(fake_immich, "09:00:00", **A)  # same camera (Canon), an hour earlier
    add(fake_immich, "09:55:00", **B, **PHONE)  # another camera, 5 minutes earlier
    target = add(fake_immich, "10:00:00")
    sync(signed_in)
    url = f"/api/assets/{local_id(signed_in, fake_immich, target)}/suggestions"
    same = time_neighbors(signed_in.get(url, params={"same_camera_only": True}).json())
    assert [p["camera"] for p in same["track"]] == ["Canon EOS 300D"]
    # The other cameras show as excluded; the photo's own one stays in.
    assert [(c["same_camera"], c["excluded"]) for c in same["cameras"]] == [
        (True, False),
        (False, True),
    ]


def test_only_this_camera_needs_a_known_camera(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    add(fake_immich, "09:55:00", **B, **PHONE)
    target = fake_immich.add_asset(taken="2024-05-01T10:00:00", exif={"make": None, "model": None})
    sync(signed_in)
    url = f"/api/assets/{local_id(signed_in, fake_immich, target)}/suggestions"
    result = time_neighbors(signed_in.get(url, params={"same_camera_only": True}).json())
    # Nothing to compare with: the mode is ignored rather than hiding every neighbor.
    assert [p["camera"] for p in result["track"]] == ["Apple iPhone 15 Pro Max"]


def test_neighbors_carry_the_version_of_their_thumbnails(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    neighbor = add(fake_immich, "10:00:00", **A)
    fake_immich.assets[neighbor]["thumbhash"] = "rotated-1"
    target = add(fake_immich, "10:10:00")
    result = m1(signed_in, fake_immich, target)
    assert result["track"][0]["version"] == "rotated-1"
    assert result["candidates"][0]["evidence"]["neighbors"][0]["version"] == "rotated-1"


def test_a_location_saved_a_moment_ago_counts_at_once(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    before = add(fake_immich, "09:50:00")
    target = add(fake_immich, "10:00:00")
    sync(signed_in)
    before_id = local_id(signed_in, fake_immich, before)
    url = f"/api/assets/{local_id(signed_in, fake_immich, target)}/suggestions"
    assert time_neighbors(signed_in.get(url).json())["note"] == "no_neighbors"

    pending = f"{before_id},{A['latitude']},{A['longitude']}"
    result = time_neighbors(signed_in.get(url, params={"pending": pending}).json())
    [candidate] = result["candidates"]
    assert (candidate["latitude"], candidate["longitude"]) == (A["latitude"], A["longitude"])
    # Shown as it will be once sent: nothing changes on the screen when it is.
    assert candidate["evidence"]["neighbors"][0]["estimated"] is True
    assert result["track"][0]["estimated"] is True
    # Nothing is written: without the parameter the photo is still without a location.
    assert time_neighbors(signed_in.get(url).json())["note"] == "no_neighbors"

    bad = signed_in.get(url, params={"pending": "x,1,2"})
    assert (bad.status_code, bad.json()["code"]) == (422, "pending_invalid")
