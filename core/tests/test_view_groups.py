# SPDX-License-Identifier: AGPL-3.0-or-later
"""Groups of photos of one view: the core rule, the neighbors kept per photo, the rebuilds."""

import math
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import FakeImmich, run_jobs, sync
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_embeddings import encoded, run_module, start_worker

from steward import view_groups
from steward.models import EMBEDDING_DIM, Account, Asset, Job, ViewGroup, ViewGroupMember
from steward.view_groups import ATTACHED, CORE, cluster, matched, merged

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
    assert view("spread") == [str(kitchen)]
    assert set(view("all")) == {str(yard), str(kitchen)}
    assert view("trash") == []

    in_db(signed_in, update(ViewGroup).where(ViewGroup.id == kitchen).values(trash=True))
    assert view("all") == [str(yard)]
    assert view("trash") == [str(kitchen)]
    counts = signed_in.get("/api/groups").json()["counts"]
    assert counts == {"all": 1, "no_location": 0, "spread": 0, "trash": 1}

    group = signed_in.get(f"/api/groups/{kitchen}").json()
    assert group["group"]["without_location"] == 3
    assert group["group"]["spread"] is True
    assert [p["file_name"] for p in group["photos"]] == [f"kitchen{i}.jpg" for i in range(5)]


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
