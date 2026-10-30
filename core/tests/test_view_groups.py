# SPDX-License-Identifier: AGPL-3.0-or-later
"""Groups of photos of one view: the core rule, the neighbors kept per photo, the rebuilds."""

import math
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import FakeImmich, run_jobs, sync
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update
from test_embeddings import encoded, run_module, start_worker

from steward import similar_hints, view_groups
from steward.models import (
    EMBEDDING_DIM,
    Account,
    Asset,
    Job,
    LocationChange,
    ViewGroup,
    ViewGroupMember,
)
from steward.view_groups import (
    ATTACHED,
    CORE,
    Rule,
    build,
    center_of,
    closeness,
    cluster,
    gathered,
    matched,
    merged,
    parts_of,
    spot_of,
    spots_of,
    uncut,
)

# --- The rule, without a database -----------------------------------------------------------------


def ids(count: int) -> list[UUID]:
    return [uuid4() for _ in range(count)]


def both_ways(pairs: list[tuple[UUID, UUID, float]]) -> list[tuple[UUID, UUID, float]]:
    return pairs + [(b, a, s) for a, b, s in pairs]


def clique(photos: list[UUID], similarity: float = 0.9) -> list[tuple[UUID, UUID, float]]:
    return both_ways([(a, b, similarity) for i, a in enumerate(photos) for b in photos[i + 1 :]])


def test_cores_close_to_each_other_are_one_group() -> None:
    first, second = ids(4), ids(4)
    groups = cluster(clique(first) + clique(second), core_neighbors=3)
    assert [set(g) for g in groups] == [set(first), set(second)] or [set(g) for g in groups] == [
        set(second),
        set(first),
    ]
    assert all(role == CORE for g in groups for role in g.values())


def test_a_photo_close_to_two_groups_joins_the_more_similar_and_links_none() -> None:
    first, second = ids(4), ids(4)
    between = uuid4()
    pairs = clique(first) + clique(second)
    pairs += [(between, first[0], 0.5), (between, second[0], 0.7)]
    groups = cluster(pairs, core_neighbors=3)
    assert len(groups) == 2
    with_between = next(g for g in groups if between in g)
    assert set(with_between) == {*second, between}
    assert with_between[between] == ATTACHED


def test_too_few_close_neighbors_make_no_group() -> None:
    assert cluster(clique(ids(3)), core_neighbors=3) == []


def test_a_new_neighbor_takes_its_place_in_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view_groups, "NEIGHBORS", 3)
    a, b, c, new = ids(4)
    assert merged([a, b, c], [0.9, 0.8, 0.7], new, 0.85) == ([a, new, b], [0.9, 0.85, 0.8])
    assert merged([a, b, c], [0.9, 0.8, 0.7], new, 0.6) is None
    assert merged([a, b], [0.9, 0.8], new, 0.1) == ([a, b, new], [0.9, 0.8, 0.1])
    # A photo with a new vector: its older entry goes.
    assert merged([a, b, c], [0.9, 0.8, 0.7], b, 0.95) == ([b, a, c], [0.95, 0.9, 0.7])


def two_beaches() -> tuple[list[UUID], list[UUID], list[tuple[UUID, UUID, float]]]:
    """Close inside (0.8), and just close to each other (0.45)."""
    first, second = ids(6), ids(6)
    pairs = clique(first, 0.8) + clique(second, 0.8)
    return first, second, pairs + both_ways(list(zip(first, second, [0.45] * 6, strict=True)))


RULE = Rule(similarity=0.4, core_neighbors=3, mutual=True)


def test_a_large_group_far_apart_is_built_again_stricter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view_groups, "SPLIT_FROM", 10)
    first, second, pairs = two_beaches()
    places = {p: (42.4, 19.26) for p in first[:3]} | {p: (45.0, 7.0) for p in second[:3]}
    found = {frozenset(g) for g in build(pairs, places, RULE)}
    assert found == {frozenset(first), frozenset(second)}


def test_a_group_in_one_spot_stays_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view_groups, "SPLIT_FROM", 10)
    first, second, pairs = two_beaches()
    places = {p: (42.4, 19.26) for p in first + second}
    assert [len(g) for g in build(pairs, places, RULE)] == [12]


def test_a_group_with_too_few_locations_stays_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view_groups, "SPLIT_FROM", 10)
    first, _, pairs = two_beaches()
    assert [len(g) for g in build(pairs, {first[0]: (42.4, 19.26)}, RULE)] == [12]


def test_a_small_group_far_apart_stays_whole() -> None:
    first, second, pairs = two_beaches()
    places = {p: (42.4, 19.26) for p in first[:3]} | {p: (45.0, 7.0) for p in second[:3]}
    assert [len(g) for g in build(pairs, places, RULE)] == [12]


def test_photos_that_find_no_place_in_the_parts_leave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view_groups, "SPLIT_FROM", 10)
    first, second, pairs = two_beaches()
    stray = uuid4()
    pairs += both_ways([(stray, first[0], 0.45), (stray, second[0], 0.45)])
    places = {p: (42.4, 19.26) for p in first[:3]} | {p: (45.0, 7.0) for p in second[:3]}
    found = build(pairs, places, RULE)
    assert not any(stray in g for g in found)
    assert sum(len(g) for g in found) == 12


def test_splitting_stops_at_the_top(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view_groups, "SPLIT_FROM", 10)
    photos = ids(12)
    places = {p: (40.0 + i, 10.0) for i, p in enumerate(photos)}  # no two in one spot
    found = build(clique(photos, 0.95), places, RULE)
    assert [len(g) for g in found] == [12]


def two_held_by_one() -> tuple[list[UUID], list[UUID], UUID, list[tuple[UUID, UUID, float]]]:
    """Two sets of photos, not close to each other, both close to one photo (the dog)."""
    first, second, dog = ids(4), ids(4), uuid4()
    pairs = clique(first) + clique(second)
    pairs += both_ways([(dog, p, 0.6) for p in first[:3] + second[:3]])
    return first, second, dog, pairs


def test_a_photo_in_the_trash_links_nothing() -> None:
    first, second, dog, pairs = two_held_by_one()
    assert [len(g) for g in cluster(pairs, 3)] == [9]
    found = cluster(uncut(pairs, {dog}, {}, {}), 3)
    assert {frozenset(g) for g in found} == {frozenset(first), frozenset(second)}


def test_a_photo_taken_out_links_nothing_in_that_group() -> None:
    first, second, dog, pairs = two_held_by_one()
    group = uuid4()
    found = cluster(uncut(pairs, set(), {group: {dog}}, {group: {*first, *second}}), 3)
    assert {frozenset(g) for g in found} == {frozenset(first), frozenset(second)}

    # In another group it still may.
    other = uuid4()
    kept = uncut(pairs, set(), {other: {dog}}, {group: {*first, *second}})
    assert [len(g) for g in cluster(kept, 3)] == [9]


def test_a_new_cluster_continues_the_old_group_sharing_most_photos() -> None:
    old_a, old_b = uuid4(), uuid4()
    photos = ids(6)
    old = {old_a: set(photos[:3]), old_b: set(photos[3:])}
    clusters = [
        {p: CORE for p in photos[:4]},  # three of A, one of B
        {p: CORE for p in photos[4:]},  # two of B
        {p: CORE for p in ids(4)},  # new
    ]
    assert matched(clusters, old) == {0: old_a, 1: old_b}


# --- With the database ----------------------------------------------------------------------------


def scene(axis: int, variant: int) -> list[float]:
    """Photos of one scene: similarity ~0.92 to each other, 0 to other scenes."""
    values = [0.0] * EMBEDDING_DIM
    values[axis] = 1.0
    values[100 + 10 * axis + variant] = 0.3
    norm = math.sqrt(1.09)
    return [v / norm for v in values]


@pytest.fixture(autouse=True)
def rebuild_whenever(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view_groups, "REBUILD_EVERY", timedelta(0))


@pytest.fixture
def library(signed_in: TestClient, fake_immich: FakeImmich) -> dict[str, str]:
    """Name -> id: five photos of a yard, five of a kitchen, one alone."""
    vectors = {f"yard{i}.jpg": scene(0, i) for i in range(5)}
    vectors |= {f"kitchen{i}.jpg": scene(1, i) for i in range(5)}
    vectors["alone.jpg"] = scene(2, 0)
    for minute, name in enumerate(vectors):
        fake_immich.add_asset(taken=f"2024-05-01T10:{minute:02}:00", originalFileName=name)
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    by_name = {item["file_name"]: item["id"] for item in items}
    worker = start_worker(signed_in)
    for name, vector in vectors.items():
        run_module(signed_in, worker, by_name[name], {"embedding": encoded(vector)})
    return by_name


def schedule(client: TestClient) -> None:
    runner = client.app.state.job_runner  # type: ignore[attr-defined]
    client.portal.call(runner.schedule_view_groups)  # type: ignore[union-attr]
    run_jobs(client)


def groups(client: TestClient, names: dict[str, str]) -> dict[UUID, dict[str, str]]:
    """Group id -> photo name -> role."""
    by_id = {UUID(i): name for name, i in names.items()}

    async def read() -> dict[UUID, dict[str, str]]:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            rows = await db.execute(
                select(ViewGroupMember.group_id, ViewGroupMember.asset_id, ViewGroupMember.role)
            )
            result: dict[UUID, dict[str, str]] = {}
            for group_id, asset_id, role in rows:
                result.setdefault(group_id, {})[by_id[asset_id]] = role
            return result

    return client.portal.call(read)  # type: ignore[union-attr]


def in_db(client: TestClient, statement: Any) -> None:
    async def write() -> None:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            await db.execute(statement)
            await db.commit()

    client.portal.call(write)  # type: ignore[union-attr]


def names_of(found: dict[UUID, dict[str, str]]) -> list[set[str]]:
    return sorted((set(g) for g in found.values()), key=sorted)


def test_photos_of_one_view_are_grouped(signed_in: TestClient, library: dict[str, str]) -> None:
    schedule(signed_in)
    found = groups(signed_in, library)
    assert names_of(found) == [
        {f"kitchen{i}.jpg" for i in range(5)},
        {f"yard{i}.jpg" for i in range(5)},
    ]
    assert all(role == CORE for g in found.values() for role in g.values())

    # Nothing new: the next schedule starts no job.
    async def due() -> bool:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            account_id = await db.scalar(select(Account.id))
            assert account_id is not None
            return await view_groups.is_due(db, account_id)

    assert not signed_in.portal.call(due)  # type: ignore[union-attr]


def test_a_long_first_pass_goes_on_in_further_jobs(
    signed_in: TestClient, library: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(view_groups, "BATCH", 4)
    monkeypatch.setattr(view_groups, "SEARCH_FOR", timedelta(0))
    schedule(signed_in)
    assert len(groups(signed_in, library)) == 2
    jobs = signed_in.portal.call(view_group_jobs, signed_in)  # type: ignore[union-attr]
    # 11 photos, 4 per job; only the last one rebuilds.
    assert [(job["searched"], job["left"], job["rebuilt"]) for job in jobs] == [
        (4, 7, False),
        (4, 3, False),
        (3, 0, True),
    ]


async def view_group_jobs(client: TestClient) -> list[dict[str, Any]]:
    async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        rows = await db.scalars(
            select(Job).where(Job.kind == view_groups.JOB_KIND).order_by(Job.created_at)
        )
        return [job.progress for job in rows]


def test_a_rebuild_splits_a_scattered_group_and_one_part_keeps_its_name(
    signed_in: TestClient, fake_immich: FakeImmich, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(view_groups, "SPLIT_FROM", 5)
    # Similarity ~0.97 inside a beach, ~0.49 between the two.
    vectors = {}
    for beach, axis in (("north", 1), ("south", 2)):
        for i in range(4):
            values = [0.0] * EMBEDDING_DIM
            values[0], values[axis], values[200 + 10 * axis + i] = 0.7, 0.7, 0.14
            vectors[f"{beach}{i}.jpg"] = values
    for minute, name in enumerate(vectors):
        fake_immich.add_asset(taken=f"2024-05-01T10:{minute:02}:00", originalFileName=name)
    sync(signed_in)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    names = {item["file_name"]: item["id"] for item in items}
    worker = start_worker(signed_in)
    for name, vector in vectors.items():
        run_module(signed_in, worker, names[name], {"embedding": encoded(vector)})

    schedule(signed_in)
    found = groups(signed_in, names)
    assert [len(g) for g in found.values()] == [8]
    whole = next(iter(found))
    in_db(signed_in, update(ViewGroup).where(ViewGroup.id == whole).values(name="Beaches"))

    for name in names:
        locate(signed_in, names[name], *((42.4, 19.26) if "north" in name else (45.0, 7.0)))
    signed_in.put("/api/settings", json={"groups_core_neighbors": 2})
    run_jobs(signed_in)

    found = groups(signed_in, names)
    assert names_of(found) == [
        {f"north{i}.jpg" for i in range(4)},
        {f"south{i}.jpg" for i in range(4)},
    ]
    assert whole in found


def test_a_new_photo_joins_its_group(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    schedule(signed_in)
    fake_immich.add_asset(taken="2024-05-01T11:00:00", originalFileName="yard9.jpg")
    sync(signed_in, full=True)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    library = {item["file_name"]: item["id"] for item in items}
    worker = start_worker(signed_in)
    run_module(signed_in, worker, library["yard9.jpg"], {"embedding": encoded(scene(0, 9))})
    schedule(signed_in)
    yard = next(g for g in groups(signed_in, library).values() if "yard0.jpg" in g)
    assert set(yard) == {f"yard{i}.jpg" for i in (0, 1, 2, 3, 4, 9)}


def test_a_rebuild_keeps_the_name_and_what_the_user_took_out(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard_id = next(i for i, g in groups(signed_in, library).items() if "yard0.jpg" in g)
    in_db(signed_in, update(ViewGroup).where(ViewGroup.id == yard_id).values(name="Yard"))
    in_db(
        signed_in,
        update(ViewGroupMember)
        .where(ViewGroupMember.asset_id == UUID(library["yard4.jpg"]))
        .values(role="excluded"),
    )

    # A new threshold rebuilds the groups at once.
    response = signed_in.put("/api/settings", json={"groups_similarity": 0.5})
    assert response.json()["groups_similarity"] == 0.5
    run_jobs(signed_in)

    found = groups(signed_in, library)
    assert found[yard_id] == {f"yard{i}.jpg": CORE for i in range(4)} | {"yard4.jpg": "excluded"}

    async def name() -> str | None:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            group = await db.get(ViewGroup, yard_id)
            return group.name if group else None

    assert signed_in.portal.call(name) == "Yard"  # type: ignore[union-attr]


def test_too_strict_a_rule_removes_the_groups(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    signed_in.put("/api/settings", json={"groups_core_neighbors": 5})
    run_jobs(signed_in)
    assert groups(signed_in, library) == {}


@pytest.mark.parametrize(
    "body",
    [{"groups_similarity": 0.05}, {"groups_similarity": 1.0}, {"groups_core_neighbors": 0}],
)
def test_thresholds_out_of_range_are_refused(signed_in: TestClient, body: dict[str, Any]) -> None:
    assert signed_in.put("/api/settings", json=body).status_code == 422


def locate(client: TestClient, asset_id: str, latitude: float, longitude: float) -> None:
    in_db(
        client,
        update(Asset)
        .where(Asset.id == UUID(asset_id))
        .values(latitude=latitude, longitude=longitude),
    )


def group_of(client: TestClient, names: dict[str, str], photo: str) -> UUID:
    return next(i for i, g in groups(client, names).items() if photo in g)


def test_the_list_named_first_then_the_largest(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    kitchen = group_of(signed_in, library, "kitchen0.jpg")
    in_db(
        signed_in,
        update(ViewGroupMember)
        .where(ViewGroupMember.asset_id == UUID(library["yard4.jpg"]))
        .values(role="excluded"),
    )

    answer = signed_in.get("/api/groups").json()
    assert answer["status"]["vectors"] == answer["status"]["searched"] == 11
    assert answer["status"]["rebuilt_at"] is not None
    assert [g["id"] for g in answer["groups"]] == [str(kitchen), str(yard)]
    assert [g["photos"] for g in answer["groups"]] == [5, 4]
    in_kitchen = {library[f"kitchen{i}.jpg"] for i in range(5)}
    assert answer["groups"][0]["cover"]["id"] in in_kitchen

    assert signed_in.patch(f"/api/groups/{yard}", json={"name": " Yard "}).status_code == 200
    answer = signed_in.get("/api/groups").json()
    assert [(g["name"], g["id"]) for g in answer["groups"]] == [
        ("Yard", str(yard)),
        (None, str(kitchen)),
    ]
    assert len(signed_in.get("/api/groups", params={"limit": 1, "offset": 1}).json()["groups"]) == 1

    # An empty name takes it away.
    assert (
        signed_in.patch(f"/api/groups/{yard}", json={"name": " "}).json()["group"]["name"] is None
    )


def test_the_views_of_the_list(signed_in: TestClient, library: dict[str, str]) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    kitchen = group_of(signed_in, library, "kitchen0.jpg")
    for i in range(5):  # the yard is all in one spot
        locate(signed_in, library[f"yard{i}.jpg"], 42.4, 19.26)
    locate(signed_in, library["kitchen0.jpg"], 42.4, 19.26)
    locate(signed_in, library["kitchen1.jpg"], 45.0, 19.26)  # far from the first
    in_db(signed_in, update(ViewGroup).where(ViewGroup.id == yard).values(trash=False))

    def view(name: str) -> list[str]:
        answer = signed_in.get("/api/groups", params={"view": name}).json()
        return [g["id"] for g in answer["groups"]]

    assert view("no_location") == [str(kitchen)]
    assert set(view("with_location")) == {str(yard), str(kitchen)}
    assert view("spread") == [str(kitchen)]
    assert set(view("all")) == {str(yard), str(kitchen)}
    assert view("trash") == []

    in_db(signed_in, update(ViewGroup).where(ViewGroup.id == kitchen).values(trash=True))
    assert view("all") == [str(yard)]
    assert view("trash") == [str(kitchen)]
    counts = signed_in.get("/api/groups").json()["counts"]
    assert counts == {
        "all": 1,
        "ready": 0,
        "no_location": 0,
        "with_location": 1,
        "spread": 0,
        "trash": 1,
        "dissolved": 0,
    }

    group = signed_in.get(f"/api/groups/{kitchen}").json()
    assert group["group"]["without_location"] == 3
    assert group["group"]["with_location"] == 2
    assert group["group"]["spread"] is True
    assert [p["file_name"] for p in group["photos"]] == [f"kitchen{i}.jpg" for i in range(5)]


def test_how_close_the_photos_of_a_group_are(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    group = signed_in.get(f"/api/groups/{yard}").json()
    assert group["group"]["similarity"] == pytest.approx(0.917, abs=0.01)
    assert set(group["closeness"]) == {library[f"yard{i}.jpg"] for i in range(5)}
    assert all(s == pytest.approx(0.917, abs=0.01) for s in group["closeness"].values())

    # A photo taken out no longer counts, and is no longer counted for the others.
    signed_in.post(f"/api/groups/{yard}/exclude", json={"ids": [library["yard4.jpg"]]})
    assert library["yard4.jpg"] not in signed_in.get(f"/api/groups/{yard}").json()["closeness"]


def test_closeness_is_the_median_of_the_photos() -> None:
    a, b, c, stray = ids(4)
    pairs = clique([a, b, c], 0.9) + both_ways([(stray, a, 0.3)])
    assert closeness([{a: CORE, b: CORE, c: CORE, stray: ATTACHED}], pairs) == [0.8]
    assert closeness([{a: CORE}], []) == [None]


def test_a_reset_drops_the_groups_with_all_done_to_them_but_not_the_trash(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    signed_in.patch(f"/api/groups/{yard}", json={"name": "Yard", "trash": True})
    signed_in.post(f"/api/groups/{yard}/exclude", json={"ids": [library["yard4.jpg"]]})
    signed_in.post(f"/api/groups/{yard}/trash", json={"ids": [library["yard3.jpg"]]})

    # While the job those asked for waits, a reset is refused.
    refused = signed_in.post("/api/groups/reset")
    assert (refused.status_code, refused.json()["code"]) == (409, "groups_busy")
    run_jobs(signed_in)

    assert signed_in.post("/api/groups/reset").status_code == 202
    run_jobs(signed_in)

    found = signed_in.get("/api/groups").json()
    assert all(g["name"] is None and not g["trash"] for g in found["groups"])
    new_yard = group_of(signed_in, library, "yard0.jpg")
    assert new_yard != yard
    assert groups(signed_in, library)[new_yard]["yard4.jpg"] == CORE  # taken out no more
    assert "yard3.jpg" not in groups(signed_in, library)[new_yard]  # still in the trash
    assert signed_in.get("/api/groups/trash-photos").json()["total"] == 1


def test_the_center_of_a_group() -> None:
    photos = ids(40)
    closeness_of = {p: i / 100 for i, p in enumerate(photos)}
    assert center_of(closeness_of) == photos[:33:-1]  # 15 %, closest first
    few = {p: 0.5 for p in photos[:4]}
    assert len(center_of(few)) == 3
    assert center_of({}) == []


def test_the_center_comes_with_the_group(signed_in: TestClient, library: dict[str, str]) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    group = signed_in.get(f"/api/groups/{yard}").json()
    assert len(group["center"]) == 3
    assert set(group["center"]) <= {library[f"yard{i}.jpg"] for i in range(5)}


def test_a_dissolved_group_is_not_built_again_and_comes_back_with_its_name(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    signed_in.patch(f"/api/groups/{yard}", json={"name": "Yard"})

    assert signed_in.post(f"/api/groups/{yard}/dissolve").status_code == 202
    run_jobs(signed_in)
    found = groups(signed_in, library)
    assert all(role == "excluded" for role in found[yard].values())
    assert not any("yard0.jpg" in g and g["yard0.jpg"] != "excluded" for g in found.values())
    answer = signed_in.get("/api/groups").json()
    assert all(g["id"] != str(yard) for g in answer["groups"])
    assert answer["counts"]["dissolved"] == 1

    # Rebuilds keep it apart.
    signed_in.put("/api/settings", json={"groups_similarity": 0.5})
    run_jobs(signed_in)
    assert yard in groups(signed_in, library)
    listed = signed_in.get("/api/groups", params={"view": "dissolved"}).json()["groups"]
    assert [(g["id"], g["name"], g["photos"]) for g in listed] == [(str(yard), "Yard", 5)]
    assert listed[0]["cover"] is not None

    assert signed_in.post(f"/api/groups/{yard}/bring-back").status_code == 202
    run_jobs(signed_in)
    answer = signed_in.get("/api/groups").json()
    assert answer["counts"]["dissolved"] == 0
    assert ("Yard", 5) in [(g["name"], g["photos"]) for g in answer["groups"]]


def test_two_photos_of_a_dissolved_group_link_nothing_but_others_do() -> None:
    a, b, other = ids(3)
    group = uuid4()
    pairs = both_ways([(a, b, 0.9), (a, other, 0.9)])
    kept = uncut(pairs, set(), {group: {a, b}}, {}, {group})
    assert {(x, y) for x, y, _ in kept} == {(a, other), (other, a)}
    # A group only taken out of keeps them linked to each other.
    assert len(uncut(pairs, set(), {group: {a, b}}, {})) == 4


def test_a_group_nobody_has(signed_in: TestClient) -> None:
    assert signed_in.get(f"/api/groups/{uuid4()}").json()["code"] == "group_not_found"
    assert signed_in.patch(f"/api/groups/{uuid4()}", json={"name": "x"}).status_code == 404


def test_the_button_searches_all_the_photos_again(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    assert signed_in.post("/api/groups/refresh").status_code == 202
    run_jobs(signed_in)
    progress = signed_in.portal.call(view_group_jobs, signed_in)  # type: ignore[union-attr]
    assert progress[-1]["searched"] == 11
    assert progress[-1]["rebuilt"] is True
    assert len(groups(signed_in, library)) == 2


def test_the_map_points_are_the_photos_with_a_location(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    locate(signed_in, library["yard0.jpg"], 42.4, 19.26)
    locate(signed_in, library["yard1.jpg"], 0, 0)  # what Immich takes for "no location"
    group = signed_in.get(f"/api/groups/{group_of(signed_in, library, 'yard0.jpg')}").json()
    assert group["points"] == [
        {
            "id": library["yard0.jpg"],
            "latitude": 42.4,
            "longitude": 19.26,
            "spot": 0,
            "set_in_app": False,
        }
    ]


def test_a_photo_taken_out_comes_back_by_hand_and_stays(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    photo = library["yard4.jpg"]

    answer = signed_in.post(f"/api/groups/{yard}/exclude", json={"ids": [photo]}).json()
    assert [p["file_name"] for p in answer["excluded"]] == ["yard4.jpg"]
    assert answer["group"]["photos"] == 4

    answer = signed_in.post(f"/api/groups/{yard}/include", json={"ids": [photo]}).json()
    assert answer["excluded"] == []
    assert answer["group"]["photos"] == 5
    assert groups(signed_in, library)[yard]["yard4.jpg"] == "added"

    # A rebuild leaves it as the user put it, and does not repeat it as found by the rule.
    signed_in.put("/api/settings", json={"groups_similarity": 0.5})
    run_jobs(signed_in)
    assert groups(signed_in, library)[yard]["yard4.jpg"] == "added"


def test_a_photo_added_to_a_group_leaves_its_old_one(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    kitchen = group_of(signed_in, library, "kitchen0.jpg")
    signed_in.post(f"/api/groups/{yard}/include", json={"ids": [library["kitchen0.jpg"]]})
    found = groups(signed_in, library)
    assert "kitchen0.jpg" in found[yard]
    assert "kitchen0.jpg" not in found[kitchen]


def test_the_photos_just_short_of_a_group(
    signed_in: TestClient, fake_immich: FakeImmich, library: dict[str, str]
) -> None:
    fake_immich.add_asset(taken="2024-05-01T11:00:00", originalFileName="almost.jpg")
    sync(signed_in, full=True)
    items = signed_in.get("/api/assets", params={"month": "2024-05"}).json()
    library = {item["file_name"]: item["id"] for item in items}
    # Similarity to the yard: ~0.42, under the 0.47 of a group, above 0.37.
    vector = [0.0] * EMBEDDING_DIM
    vector[0], vector[300] = 0.44, 0.898
    worker = start_worker(signed_in)
    run_module(signed_in, worker, library["almost.jpg"], {"embedding": encoded(vector)})
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    kitchen = group_of(signed_in, library, "kitchen0.jpg")

    assert [p["file_name"] for p in signed_in.get(f"/api/groups/{yard}/near").json()] == [
        "almost.jpg"
    ]
    assert signed_in.get(f"/api/groups/{kitchen}/near").json() == []

    signed_in.post(f"/api/groups/{yard}/include", json={"ids": [library["almost.jpg"]]})
    assert signed_in.get(f"/api/groups/{yard}/near").json() == []


def test_a_photo_with_only_trash_around_gets_its_hint_once(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    location = {"latitude": 42.4, "longitude": 19.26}
    assert signed_in.put(f"/api/assets/{library['yard0.jpg']}/location", json=location).is_success
    yard = group_of(signed_in, library, "yard0.jpg")
    signed_in.patch(f"/api/groups/{yard}", json={"trash": True})
    signed_in.post("/api/library/similar-hints")
    run_jobs(signed_in)

    async def due() -> bool:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            account_id = await db.scalar(select(Account.id))
            assert account_id is not None
            return await similar_hints.any_due(db, account_id)

    assert not signed_in.portal.call(due)  # type: ignore[union-attr]


def test_a_photo_in_the_trash_suggests_no_place_and_stays_out(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    location = {"latitude": 42.4, "longitude": 19.26}
    assert signed_in.put(f"/api/assets/{library['yard0.jpg']}/location", json=location).is_success
    yard = group_of(signed_in, library, "yard0.jpg")

    def similar_candidates() -> list[Any]:
        blocks = signed_in.get(f"/api/assets/{library['yard1.jpg']}/suggestions").json()
        return next(b for b in blocks if b["key"] == "similar")["candidates"]

    assert len(similar_candidates()) == 1

    answer = signed_in.post(f"/api/groups/{yard}/trash", json={"ids": [library["yard0.jpg"]]})
    assert answer.status_code == 200
    assert answer.json()["group"]["photos"] == 4
    assert similar_candidates() == []
    trash = signed_in.get("/api/groups/trash-photos").json()
    assert (trash["total"], [p["file_name"] for p in trash["photos"]]) == (1, ["yard0.jpg"])
    assert signed_in.get(f"/api/groups/{yard}/near").json() == []

    # The rebuild it asked for leaves it out, and the group goes on.
    run_jobs(signed_in)
    found = groups(signed_in, library)[yard]
    assert found["yard0.jpg"] == "excluded"
    assert sum(role != "excluded" for role in found.values()) == 4

    detail = signed_in.get(f"/api/groups/{yard}").json()
    assert [p["file_name"] for p in detail["marked"]] == ["yard0.jpg"]
    assert detail["excluded"] == []
    assert detail["group"]["photos"] == 4

    restored = signed_in.post(
        "/api/groups/trash-photos/restore", json={"ids": [library["yard0.jpg"]]}
    )
    assert restored.json() == {"total": 0, "photos": []}
    run_jobs(signed_in)
    assert groups(signed_in, library)[yard]["yard0.jpg"] != "excluded"
    assert signed_in.get(f"/api/groups/{yard}").json()["marked"] == []
    assert len(similar_candidates()) == 1


def test_taking_a_photo_out_asks_for_a_rebuild(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    signed_in.post(f"/api/groups/{yard}/exclude", json={"ids": [library["yard4.jpg"]]})
    before = len(signed_in.portal.call(view_group_jobs, signed_in))  # type: ignore[union-attr]
    run_jobs(signed_in)
    jobs = signed_in.portal.call(view_group_jobs, signed_in)  # type: ignore[union-attr]
    assert len(jobs) == before
    assert jobs[-1]["rebuilt"] is True
    assert groups(signed_in, library)[yard]["yard4.jpg"] == "excluded"


def test_the_trash_of_another_group_is_not_reached(signed_in: TestClient) -> None:
    response = signed_in.post(f"/api/groups/{uuid4()}/trash", json={"ids": [str(uuid4())]})
    assert response.status_code == 404


def test_the_photos_of_a_trash_group_suggest_no_place(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    location = {"latitude": 42.4, "longitude": 19.26}
    assert signed_in.put(f"/api/assets/{library['yard0.jpg']}/location", json=location).is_success

    def similar_candidates() -> list[Any]:
        blocks = signed_in.get(f"/api/assets/{library['yard1.jpg']}/suggestions").json()
        return next(b for b in blocks if b["key"] == "similar")["candidates"]

    assert len(similar_candidates()) == 1

    yard = group_of(signed_in, library, "yard0.jpg")
    response = signed_in.patch(f"/api/groups/{yard}", json={"trash": True})
    assert response.json()["group"]["trash"] is True
    assert response.json()["group"]["name"] is None
    assert similar_candidates() == []

    # A photo taken out of the group is a place again.
    signed_in.post(f"/api/groups/{yard}/exclude", json={"ids": [library["yard0.jpg"]]})
    assert len(similar_candidates()) == 1


def test_the_places_of_the_group_are_suggested_for_its_photos(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    locate(signed_in, library["yard0.jpg"], 42.4, 19.26)
    locate(signed_in, library["yard1.jpg"], 42.4, 19.2601)
    locate(signed_in, library["yard2.jpg"], 45.0, 7.0)

    def blocks(ids: list[str], group: UUID | None) -> dict[str, Any]:
        body = {"ids": ids, "group_id": str(group) if group else None}
        response = signed_in.post("/api/selection/suggestions", json=body)
        assert response.status_code == 200
        return {b["key"]: b for b in response.json()}

    found = blocks([library["yard3.jpg"], library["yard4.jpg"]], yard)
    places = found["group"]["candidates"]
    assert [round(c["latitude"]) for c in places] == [42, 45]  # the larger place first
    assert [(c["kind"], c["evidence"]["photos"]) for c in places] == [("group", 2), ("group", 1)]
    assert next(iter(found)) == "group"

    # A photo chosen is not a place of its own.
    found = blocks([library["yard2.jpg"]], yard)
    assert [round(c["latitude"]) for c in found["group"]["candidates"]] == [42]

    assert "group" not in blocks([library["yard3.jpg"]], None)
    refused = signed_in.post(
        "/api/selection/suggestions", json={"ids": [library["yard3.jpg"]], "group_id": str(uuid4())}
    )
    assert refused.status_code == 404


# --- Spots ----------------------------------------------------------------------------------------

YARD = (42.4231, 19.2601)
FAR = (45.0612, 7.6801)


def place(
    client: TestClient, names: dict[str, str], *photos: tuple[str, tuple[float, float]]
) -> None:
    for name, (latitude, longitude) in photos:
        locate(client, names[name], latitude, longitude)


def test_a_place_on_the_border_of_two_cells_is_one_spot() -> None:
    assert [len(spot) for spot in gathered([(42.4249, 19.26, 5), (42.4251, 19.26, 4)])] == [2]
    spot = spot_of(gathered([(42.4249, 19.26, 5), (42.4251, 19.26, 5)])[0])
    assert (round(spot.latitude, 3), spot.photos) == (42.425, 10)


def test_spots_are_numbered_from_the_largest() -> None:
    lonely, far, also_far, *main = ids(6)
    places = {lonely: (10.0, 10.0), far: FAR, also_far: FAR} | {p: YARD for p in main}
    assert spots_of(places) == {lonely: 2, far: 1, also_far: 1} | {p: 0 for p in main}


def test_a_group_is_ready_when_the_photos_with_a_location_share_a_spot(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    place(
        signed_in,
        library,
        ("yard0.jpg", YARD),
        ("yard1.jpg", YARD),
        ("yard2.jpg", YARD),
        ("kitchen0.jpg", YARD),
        ("kitchen1.jpg", YARD),
        ("kitchen2.jpg", FAR),
        ("kitchen3.jpg", FAR),
    )
    answer = signed_in.get("/api/groups", params={"view": "ready"}).json()
    assert answer["counts"]["ready"] == 1
    group = answer["groups"][0]
    assert group["without_location"] == 2 and group["ready"] and group["main_spot"]
    assert group["spot"]["photos"] == 3
    assert abs(group["spot"]["latitude"] - YARD[0]) < 0.001

    # The yard photos are the spot; a photo far from it is told apart.
    place(signed_in, library, ("yard3.jpg", FAR))
    detail = signed_in.get(f"/api/groups/{group['id']}").json()
    numbers = {point["id"]: point["spot"] for point in detail["points"]}
    assert numbers[library["yard0.jpg"]] == 0 and numbers[library["yard3.jpg"]] == 1
    assert detail["group"]["ready"]


def test_too_few_photos_with_a_location_name_no_spot(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    place(signed_in, library, ("yard0.jpg", YARD), ("yard1.jpg", YARD))
    assert signed_in.get("/api/groups", params={"view": "ready"}).json()["counts"]["ready"] == 0


def test_a_group_marked_as_having_no_sign_of_a_place_is_not_ready(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    place(signed_in, library, *((f"yard{i}.jpg", YARD) for i in range(3)))
    group = signed_in.get("/api/groups", params={"view": "ready"}).json()["groups"][0]
    signed_in.patch(f"/api/groups/{group['id']}", json={"trash": True})
    assert signed_in.get("/api/groups", params={"view": "ready"}).json()["counts"]["ready"] == 0


def test_groups_in_one_spot_are_shown_together(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    place(
        signed_in,
        library,
        *((f"yard{i}.jpg", YARD) for i in range(3)),
        *((f"kitchen{i}.jpg", YARD) for i in range(3)),
    )
    found = groups(signed_in, library)
    yard = next(i for i, g in found.items() if "yard0.jpg" in g)
    kitchen = next(i for i, g in found.items() if "kitchen0.jpg" in g)
    same = signed_in.get(f"/api/groups/{yard}/same-spot").json()
    assert [group["id"] for group in same] == [str(kitchen)]

    place(signed_in, library, *((f"kitchen{i}.jpg", FAR) for i in range(5)))
    assert signed_in.get(f"/api/groups/{yard}/same-spot").json() == []


# --- Parts ----------------------------------------------------------------------------------------


def test_a_group_falls_into_its_scenes() -> None:
    first, second, stray = ids(4), ids(4), uuid4()
    pairs = clique(first) + clique(second) + both_ways([(stray, first[0], 0.9)])
    found = {frozenset(part) for part in parts_of(pairs, RULE)}
    assert found == {frozenset([*first, stray]), frozenset(second)}


def test_only_mutual_pairs_make_a_scene() -> None:
    photos = ids(4)
    one_way = [(a, b, 0.9) for a in photos for b in photos if a < b]
    assert parts_of(one_way, RULE) == []


def test_the_parts_of_a_group_leave_out_those_taken_out(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    answer = signed_in.get(f"/api/groups/{yard}/parts").json()
    assert answer["similarity"] == 0.67
    assert {frozenset(part) for part in answer["parts"]} == {
        frozenset(library[f"yard{i}.jpg"] for i in range(5))
    }

    signed_in.post(f"/api/groups/{yard}/exclude", json={"ids": [library["yard4.jpg"]]})
    answer = signed_in.get(f"/api/groups/{yard}/parts", params={"level": 3}).json()
    assert answer["similarity"] == 0.77
    assert len(answer["parts"][0]) == 4

    assert signed_in.get(f"/api/groups/{yard}/parts", params={"level": 4}).status_code == 422


def test_half_of_the_photos_in_one_spot_is_no_main_spot(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    place(
        signed_in,
        library,
        ("kitchen0.jpg", YARD),
        ("kitchen1.jpg", YARD),
        ("kitchen2.jpg", FAR),
        ("kitchen3.jpg", FAR),
    )
    kitchen = group_of(signed_in, library, "kitchen0.jpg")
    group = signed_in.get(f"/api/groups/{kitchen}").json()["group"]
    assert group["spot"] is not None and not group["main_spot"] and not group["ready"]


def test_a_point_tells_a_location_set_in_the_app(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    place(signed_in, library, ("yard0.jpg", YARD), ("yard1.jpg", YARD))
    yard = group_of(signed_in, library, "yard0.jpg")

    def write(status: str, name: str) -> None:
        in_db(
            signed_in,
            insert(LocationChange).values(
                asset_id=UUID(library[name]),
                latitude=YARD[0],
                longitude=YARD[1],
                source="manual",
                status=status,
            ),
        )

    write("applied", "yard0.jpg")
    write("undone", "yard1.jpg")
    points = signed_in.get(f"/api/groups/{yard}").json()["points"]
    assert {p["id"]: p["set_in_app"] for p in points} == {
        library["yard0.jpg"]: True,
        library["yard1.jpg"]: False,
    }


def test_the_card_of_a_photo_tells_its_group(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    photo = library["yard0.jpg"]
    signed_in.patch(f"/api/groups/{yard}", json={"name": "Yard"})

    answer = signed_in.get(f"/api/groups/of-photo/{photo}").json()
    assert answer == {"group": {"id": str(yard), "name": "Yard"}, "no_sign": False}

    signed_in.patch(f"/api/groups/{yard}", json={"trash": True})
    assert signed_in.get(f"/api/groups/of-photo/{photo}").json()["no_sign"]
    signed_in.patch(f"/api/groups/{yard}", json={"trash": False})

    alone = library["alone.jpg"]
    assert signed_in.get(f"/api/groups/of-photo/{alone}").json() == {
        "group": None,
        "no_sign": False,
    }

    # Marked by itself, it stays with the group, out of its photos.
    signed_in.post(f"/api/groups/{yard}/trash", json={"ids": [photo]})
    assert signed_in.get(f"/api/groups/of-photo/{photo}").json() == {
        "group": {"id": str(yard), "name": "Yard"},
        "no_sign": True,
    }

    # Taken out by hand, it is in no group for the card.
    other = library["yard1.jpg"]
    signed_in.post(f"/api/groups/{yard}/exclude", json={"ids": [other]})
    assert signed_in.get(f"/api/groups/of-photo/{other}").json()["group"] is None


def test_a_marked_photo_stays_marked_when_a_group_comes_back(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    signed_in.post(f"/api/groups/{yard}/trash", json={"ids": [library["yard0.jpg"]]})
    signed_in.post(f"/api/groups/{yard}/dissolve")
    run_jobs(signed_in)
    signed_in.post(f"/api/groups/{yard}/bring-back")
    run_jobs(signed_in)
    assert groups(signed_in, library)[yard]["yard0.jpg"] == "excluded"


def test_the_marked_photos_come_in_pages_and_back_all_at_once(
    signed_in: TestClient, library: dict[str, str]
) -> None:
    schedule(signed_in)
    yard = group_of(signed_in, library, "yard0.jpg")
    ids = [library[f"yard{i}.jpg"] for i in range(3)]
    signed_in.post(f"/api/groups/{yard}/trash", json={"ids": ids})

    first = signed_in.get("/api/groups/trash-photos", params={"limit": 2}).json()
    second = signed_in.get("/api/groups/trash-photos", params={"offset": 2, "limit": 2}).json()
    assert (first["total"], len(first["photos"]), len(second["photos"])) == (3, 2, 1)
    assert {p["id"] for p in first["photos"] + second["photos"]} == set(ids)

    answer = signed_in.post("/api/groups/trash-photos/restore-all")
    assert answer.json() == {"total": 0, "photos": []}
    run_jobs(signed_in)
    assert groups(signed_in, library)[yard]["yard0.jpg"] != "excluded"
    assert signed_in.get(f"/api/groups/{yard}").json()["marked"] == []


def test_bringing_all_back_with_nothing_marked_is_harmless(signed_in: TestClient) -> None:
    answer = signed_in.post("/api/groups/trash-photos/restore-all")
    assert answer.json() == {"total": 0, "photos": []}
