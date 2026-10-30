# SPDX-License-Identifier: AGPL-3.0-or-later
"""Groups of photos of one view (stage 5, D-128, D-181, D-185): the tab "Environment" of the page
"Groups".

Every photo keeps its most similar photos among all the photos of the account (`ViewNeighbor`),
with a location or not. The lists depend neither on the thresholds nor on the locations, so a new
threshold or a new location needs only a rebuild of the groups, which takes seconds; the search is
done once per new vector.

The groups follow the core rule measured on the user's library (`_dev/tools/groups_bench.py`): a
photo with at least `core_neighbors` close neighbors (similarity >= `similarity`, and with
`mutual`, each keeping the other among its own neighbors) is a core; cores close to each other are
one group; any other photo joins the group of its most similar close core, but links no groups.
Photos may look alike and be far apart (beaches): a large group whose photos with a location do
not share one spot is built again, stricter, and photos that find no place in the parts leave
(D-186). This is the one thing in a rebuild that looks at the locations.
A photo in the trash links nothing, and a photo taken out of a group links nothing in that group:
the group is built as if it were not there (D-188).
A rebuild keeps the groups whose photos it finds again: their id, name, trash mark and the photos
added or taken out by the user.
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from statistics import median
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Numeric,
    Select,
    bindparam,
    cast,
    delete,
    exists,
    func,
    insert,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from steward import account_settings
from steward.embeddings import located
from steward.models import (
    EMBEDDING_DIM,
    Asset,
    Embedding,
    Job,
    LocationChange,
    ViewGroup,
    ViewGroupMember,
    ViewNeighbor,
    ViewPhotoTrash,
    utcnow,
)
from steward.modules import similar
from steward.modules.time_neighbors import distance_m

KIND = "environment"
NEIGHBORS = 30
# Photos per transaction: the progress shows, and a restart loses little.
BATCH = 100
# A job searches this long, then lets other jobs run and goes on in the next one.
SEARCH_FOR = timedelta(seconds=60)
# New photos rebuild the groups at most this often.
REBUILD_EVERY = timedelta(minutes=10)
# A rebuild at least once a day: photos moved to the trash of Immich or deleted.
REBUILD_AT_LEAST_EVERY = timedelta(hours=24)

CORE = "core"
ATTACHED = "attached"
ADDED = "added"
EXCLUDED = "excluded"
AUTO_ROLES = (CORE, ATTACHED)

# Groups from this size that do not share one spot are split (D-186, measured on a library of
# 133 thousand photos): similarity raised by a step until they do, up to the top.
SPLIT_FROM = 300
SPLIT_STEP = 0.05
SPLIT_TOP = 0.75
# One spot: this share of the photos with a location, at least this many, in a cell of ~1 km.
SPOT_SHARE = 0.7
SPOT_MIN_PHOTOS = 3
SPOT_DECIMALS = 2
# Mean latitude, mean longitude and the photos of a cell of `SPOT_DECIMALS`.
Cell = tuple[float, float, int]

# How much stricter than the group its parts are, per level of strictness.
PART_STEP = 0.1

# Photos this much less similar than a group asks for are shown next to it.
NEAR_MARGIN = 0.1
NEAR_LIMIT = 60

# The center of a group: this share of its photos, at least so many.
CENTER_SHARE = 0.15
CENTER_MIN_PHOTOS = 3

JOB_KIND = "view_groups"

_QUERY = f"CAST(:query AS halfvec({EMBEDDING_DIM}))"
# As the search of similar photos (`modules.similar`), but among all the photos.
_NEAREST = text(
    f"""
    SELECT near.asset_id, -(near.vector <#> {_QUERY}) AS similarity
    FROM (
        SELECT asset_id, vector FROM embedding
        WHERE NOT region AND account_id = :account_id AND module_id = :module_id
            AND asset_id <> :asset_id
        ORDER BY binary_quantize(vector)::bit({EMBEDDING_DIM}) <~> binary_quantize({_QUERY})
        LIMIT :pool
    ) AS near
    ORDER BY near.vector <#> {_QUERY}
    LIMIT :limit
    """
).bindparams(bindparam("query", type_=Embedding.vector.type))

# Close pairs (photo, neighbor, similarity) of the photos not in the trash of Immich.
_CLOSE = """
    WITH pair AS (
        SELECT n.asset_id AS a, p.b, p.s
        FROM view_neighbor AS n
        CROSS JOIN LATERAL unnest(n.neighbor_ids, n.similarities) AS p(b, s)
        WHERE n.account_id = :account_id
    )
    SELECT pair.a, pair.b, pair.s FROM pair
    JOIN asset AS asset_a ON asset_a.id = pair.a AND NOT asset_a.is_trashed
    JOIN asset AS asset_b ON asset_b.id = pair.b AND NOT asset_b.is_trashed
    {mutual}
    WHERE pair.s >= :similarity
"""
_MUTUAL = "JOIN pair AS back ON back.a = pair.b AND back.b = pair.a"

_PHOTO_CLOSENESS = text(
    """
    SELECT member.asset_id, avg(p.s) AS similarity
    FROM view_group_member AS member
    JOIN view_neighbor AS n ON n.asset_id = member.asset_id
    CROSS JOIN LATERAL unnest(n.neighbor_ids, n.similarities) AS p(b, s)
    JOIN view_group_member AS other
        ON other.group_id = member.group_id AND other.asset_id = p.b AND other.role <> 'excluded'
    WHERE member.group_id = :group_id AND member.role <> 'excluded'
    GROUP BY member.asset_id
    """
)

# The pairs of photos of a group, for its parts.
_GROUP_PAIRS = text(
    """
    SELECT member.asset_id AS a, p.b, p.s
    FROM view_group_member AS member
    JOIN view_neighbor AS n ON n.asset_id = member.asset_id
    CROSS JOIN LATERAL unnest(n.neighbor_ids, n.similarities) AS p(b, s)
    JOIN view_group_member AS other
        ON other.group_id = member.group_id AND other.asset_id = p.b AND other.role <> 'excluded'
    WHERE member.group_id = :group_id AND member.role <> 'excluded' AND p.s >= :similarity
    """
)

_NEAR = text(
    """
    SELECT p.b AS asset_id
    FROM view_group_member AS member
    JOIN view_neighbor AS n ON n.asset_id = member.asset_id
    CROSS JOIN LATERAL unnest(n.neighbor_ids, n.similarities) AS p(b, s)
    JOIN asset ON asset.id = p.b AND NOT asset.is_trashed
    WHERE member.group_id = :group_id AND member.role <> 'excluded' AND p.s >= :similarity
        AND NOT EXISTS (
            SELECT 1 FROM view_group_member AS other
            WHERE other.asset_id = p.b
                AND (other.role <> 'excluded' OR other.group_id = :group_id)
        )
        AND NOT EXISTS (SELECT 1 FROM view_photo_trash AS trashed WHERE trashed.asset_id = p.b)
    GROUP BY p.b
    ORDER BY max(p.s) DESC
    LIMIT :limit
    """
)


@dataclass(frozen=True)
class Rule:
    similarity: float
    core_neighbors: int
    mutual: bool


async def rule_of(db: AsyncSession, account_id: UUID) -> Rule:
    values = await account_settings.get_all(db, account_id)
    return Rule(
        similarity=float(values["groups_similarity"]),
        core_neighbors=int(values["groups_core_neighbors"]),
        mutual=bool(values["groups_mutual"]),
    )


# --- Neighbors -----------------------------------------------------------------------------------


def _due(account_id: UUID, since: datetime | None) -> Select[UUID]:
    """Photos with a vector whose neighbors are older than the vector, or than `since`."""
    stale = or_(ViewNeighbor.asset_id.is_(None), ViewNeighbor.computed_at < Embedding.created_at)
    if since is not None:
        stale = or_(stale, ViewNeighbor.computed_at < since)
    return (
        select(Embedding.asset_id)
        .outerjoin(ViewNeighbor, ViewNeighbor.asset_id == Embedding.asset_id)
        .where(
            Embedding.account_id == account_id,
            Embedding.module_id == similar.MODULE_ID,
            Embedding.region.is_(False),
            stale,
        )
        .order_by(Embedding.asset_id)
    )


async def any_due(db: AsyncSession, account_id: UUID) -> bool:
    return bool(await db.scalar(select(exists(_due(account_id, None).subquery()))))


async def nearest(
    db: AsyncSession, query: Any, account_id: UUID, asset_id: UUID
) -> list[tuple[UUID, float]]:
    """The photos of the account most similar to the vector, but the photo itself."""
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {similar.POOL}"))
    await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    rows = await db.execute(
        _NEAREST,
        {
            "query": query,
            "account_id": account_id,
            "module_id": similar.MODULE_ID,
            "asset_id": asset_id,
            "pool": similar.POOL,
            "limit": NEIGHBORS,
        },
    )
    return [(row.asset_id, float(row.similarity)) for row in rows]


def merged(
    ids: list[UUID], similarities: list[float], new_id: UUID, similarity: float
) -> tuple[list[UUID], list[float]] | None:
    """The list with the new neighbor in its place (the older entry of it dropped), or None when
    it is not among the `NEIGHBORS` most similar."""
    pairs = [(i, s) for i, s in zip(ids, similarities, strict=True) if i != new_id]
    if len(pairs) >= NEIGHBORS and similarity <= pairs[NEIGHBORS - 1][1]:
        return None
    pairs.append((new_id, similarity))
    pairs.sort(key=lambda pair: -pair[1])
    pairs = pairs[:NEIGHBORS]
    return [i for i, _ in pairs], [s for _, s in pairs]


async def _keep(
    db: AsyncSession,
    asset_id: UUID,
    account_id: UUID,
    found: list[tuple[UUID, float]],
    vector_at: datetime,
) -> None:
    """Stores the neighbors of the photo, and puts the photo among its neighbors' own when they
    were searched before its vector came and it is close enough."""
    now = datetime.now(UTC)
    row = await db.get(ViewNeighbor, asset_id)
    if row is None:
        row = ViewNeighbor(asset_id=asset_id, account_id=account_id)
        db.add(row)
    row.neighbor_ids = [i for i, _ in found]
    row.similarities = [s for _, s in found]
    row.computed_at = now
    others = await db.scalars(
        select(ViewNeighbor).where(
            ViewNeighbor.asset_id.in_([i for i, _ in found]), ViewNeighbor.computed_at < vector_at
        )
    )
    similarity_of = dict(found)
    for other in others:
        update = merged(
            list(other.neighbor_ids),
            list(other.similarities),
            asset_id,
            similarity_of[other.asset_id],
        )
        if update is not None:
            # New lists, not changed in place: the ORM sees only a new value.
            other.neighbor_ids, other.similarities = update


async def refresh_neighbors(
    db: AsyncSession,
    account_id: UUID,
    *,
    since: datetime | None = None,
    search_for: timedelta | None = None,
    on_progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, int]:
    """Searches the neighbors of the due photos (`_due`) for `search_for` at most; returns how
    many were done and how many are left."""
    due = list(await db.scalars(_due(account_id, since)))
    total, done = len(due), 0
    deadline = monotonic() + (SEARCH_FOR if search_for is None else search_for).total_seconds()
    for start in range(0, total, BATCH):
        rows = await db.execute(
            select(Embedding.asset_id, Embedding.vector, Embedding.created_at).where(
                Embedding.asset_id.in_(due[start : start + BATCH]),
                Embedding.module_id == similar.MODULE_ID,
                Embedding.region.is_(False),
            )
        )
        for asset_id, vector, vector_at in rows:
            found = await nearest(db, vector, account_id, asset_id)
            await _keep(db, asset_id, account_id, found, vector_at)
        await db.commit()
        done = min(start + BATCH, total)
        if on_progress is not None:
            await on_progress({"stage": "neighbors", "done": done, "total": total})
        # At least a batch per job, so that the next one goes on.
        if monotonic() >= deadline:
            break
    return {"searched": done, "left": total - done}


# --- Groups --------------------------------------------------------------------------------------


def cluster(
    close: Iterable[tuple[UUID, UUID, float]], core_neighbors: int
) -> list[dict[UUID, str]]:
    """Groups by the core rule from the close pairs (photo, neighbor, similarity) of each photo's
    own list: photo -> role ("core" or "attached") per group, largest first."""
    pairs: dict[UUID, list[tuple[UUID, float]]] = {}
    for a, b, s in close:
        pairs.setdefault(a, []).append((b, s))
    cores = {a for a, near in pairs.items() if len(near) >= core_neighbors}
    parent = {a: a for a in cores}

    def find(a: UUID) -> UUID:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a in cores:
        for b, _ in pairs[a]:
            if b in cores:
                root_a, root_b = find(a), find(b)
                if root_a != root_b:
                    parent[root_b] = root_a
    groups: dict[UUID, dict[UUID, str]] = {}
    for a in cores:
        groups.setdefault(find(a), {})[a] = CORE
    for a, near in pairs.items():
        if a in cores:
            continue
        best = max(((s, b) for b, s in near if b in cores), default=None)
        if best is not None:
            groups[find(best[1])][a] = ATTACHED
    return sorted(groups.values(), key=len, reverse=True)


@dataclass(frozen=True)
class Spot:
    """Where photos of a group lie together."""

    latitude: float
    longitude: float
    photos: int


def gathered(cells: Iterable[Cell]) -> list[list[Cell]]:
    """The cells of a group in spots, largest first: a spot is the largest cell left and the cells
    within `similar.JOIN_M` of it, so that a place on the border of two cells stays one."""
    left = sorted(cells, key=lambda c: (-c[2], c[0], c[1]))
    spots = []
    while left:
        seed = left[0]
        spot = [c for c in left if distance_m(seed[0], seed[1], c[0], c[1]) <= similar.JOIN_M]
        spots.append(spot)
        left = [c for c in left if c not in spot]
    spots.sort(key=lambda spot: -sum(c[2] for c in spot))
    return spots


def spot_of(cells: list[Cell]) -> Spot:
    photos = sum(c[2] for c in cells)
    return Spot(
        latitude=sum(c[0] * c[2] for c in cells) / photos,
        longitude=sum(c[1] * c[2] for c in cells) / photos,
        photos=photos,
    )


def spots_of(places: dict[UUID, tuple[float, float]]) -> dict[UUID, int]:
    """Photo -> the number of its spot in the group, 0 for the largest."""
    by_cell: dict[tuple[float, float], list[UUID]] = {}
    for asset_id, (latitude, longitude) in places.items():
        key = (round(latitude, SPOT_DECIMALS), round(longitude, SPOT_DECIMALS))
        by_cell.setdefault(key, []).append(asset_id)
    cells = {}
    for photos in by_cell.values():
        latitude = sum(places[a][0] for a in photos) / len(photos)
        longitude = sum(places[a][1] for a in photos) / len(photos)
        cells[(latitude, longitude, len(photos))] = photos
    return {
        asset_id: number
        for number, spot in enumerate(gathered(cells))
        for cell in spot
        for asset_id in cells[cell]
    }


def parts_of(pairs: list[tuple[UUID, UUID, float]], rule: Rule) -> list[list[UUID]]:
    """The scenes of a group by the rule of the groups, from pairs of the stricter similarity."""
    if rule.mutual:
        linked = {(a, b) for a, b, _ in pairs}
        pairs = [pair for pair in pairs if (pair[1], pair[0]) in linked]
    return [list(part) for part in cluster(pairs, rule.core_neighbors)]


def spot_share(members: Iterable[UUID], places: dict[UUID, tuple[float, float]]) -> float | None:
    """The share of the photos with a location in their most common spot; None with too few."""
    spots = Counter(
        (round(places[a][0], SPOT_DECIMALS), round(places[a][1], SPOT_DECIMALS))
        for a in members
        if a in places
    )
    total = sum(spots.values())
    return spots.most_common(1)[0][1] / total if total >= SPOT_MIN_PHOTOS else None


def split_scattered(
    clusters: list[dict[UUID, str]],
    close: list[tuple[UUID, UUID, float]],
    places: dict[UUID, tuple[float, float]],
    rule: Rule,
) -> list[dict[UUID, str]]:
    """The groups with the large ones that share no spot built again, stricter (see the module).
    A group with too few photos with a location stays: nothing tells that it is scattered."""
    near: dict[UUID, list[tuple[UUID, float]]] = {}
    for a, b, s in close:
        near.setdefault(a, []).append((b, s))
    done = []
    todo = [(members, rule.similarity) for members in clusters]
    while todo:
        members, similarity = todo.pop()
        share = spot_share(members, places) if len(members) >= SPLIT_FROM else None
        if share is None or share >= SPOT_SHARE or similarity >= SPLIT_TOP:
            done.append(members)
            continue
        stricter = similarity + SPLIT_STEP
        pairs = [
            (a, b, s) for a in members for b, s in near.get(a, ()) if s >= stricter and b in members
        ]
        todo.extend((part, stricter) for part in cluster(pairs, rule.core_neighbors))
    return sorted(done, key=len, reverse=True)


def uncut(
    close: list[tuple[UUID, UUID, float]],
    trash: set[UUID],
    excluded: dict[UUID, set[UUID]],
    members: dict[UUID, set[UUID]],
    dissolved: set[UUID] | None = None,
) -> list[tuple[UUID, UUID, float]]:
    """The close pairs that may link photos: none with a photo in the trash, none between a photo
    taken out of a group and the photos of that group (`members`, group -> photos), so that the
    group is built as if the photo were not there, and none between two photos of a `dissolved`
    group."""
    gone = dissolved or set()
    group_of = {a: group for group, photos in members.items() for a in photos}
    out_of: dict[UUID, set[UUID]] = {}
    for group, photos in excluded.items():
        for a in photos:
            out_of.setdefault(a, set()).add(group)

    def linked(a: UUID, b: UUID) -> bool:
        return (
            a not in trash
            and b not in trash
            and group_of.get(b) not in out_of.get(a, ())
            and group_of.get(a) not in out_of.get(b, ())
            and not (out_of.get(a, set()) & out_of.get(b, set()) & gone)
        )

    return [pair for pair in close if linked(pair[0], pair[1])]


def build(
    close: list[tuple[UUID, UUID, float]], places: dict[UUID, tuple[float, float]], rule: Rule
) -> list[dict[UUID, str]]:
    return split_scattered(cluster(close, rule.core_neighbors), close, places, rule)


def closeness(
    clusters: list[dict[UUID, str]], close: list[tuple[UUID, UUID, float]]
) -> list[float | None]:
    """Per group, how close its photos are: the median of each photo's mean similarity to the
    photos of the group among its close neighbors."""
    group_of = {a: index for index, members in enumerate(clusters) for a in members}
    totals: dict[UUID, tuple[float, int]] = {}
    for a, b, s in close:
        if a in group_of and group_of[a] == group_of.get(b):
            total, count = totals.get(a, (0.0, 0))
            totals[a] = (total + s, count + 1)
    means: list[list[float]] = [[] for _ in clusters]
    for a, (total, count) in totals.items():
        means[group_of[a]].append(total / count)
    return [round(median(values), 3) if values else None for values in means]


def matched(clusters: list[dict[UUID, str]], old: dict[UUID, set[UUID]]) -> dict[int, UUID]:
    """Which old group each new cluster continues: the one sharing most photos with it, each old
    group continued once."""
    owner = {asset: group for group, assets in old.items() for asset in assets}
    shared: Counter[tuple[int, UUID]] = Counter()
    for index, members in enumerate(clusters):
        for asset in members:
            if asset in owner:
                shared[index, owner[asset]] += 1
    result: dict[int, UUID] = {}
    taken: set[UUID] = set()
    for (index, group), _ in shared.most_common():
        if index not in result and group not in taken:
            result[index] = group
            taken.add(group)
    return result


async def rebuild(db: AsyncSession, account_id: UUID, rule: Rule) -> dict[str, Any]:
    """Builds the groups from the neighbors anew, keeping what the user did (see the module)."""
    sql = text(_CLOSE.format(mutual=_MUTUAL if rule.mutual else ""))
    close = await db.execute(sql, {"account_id": account_id, "similarity": rule.similarity})
    all_pairs = [(a, b, float(s)) for a, b, s in close]
    places = {
        row.id: (float(row.latitude), float(row.longitude))
        for row in await db.execute(
            select(Asset.id, Asset.latitude, Asset.longitude).where(
                Asset.account_id == account_id, located()
            )
        )
    }
    old: dict[UUID, set[UUID]] = {}
    # Photos the user added to a group or took out of it.
    added: dict[UUID, set[UUID]] = {}
    excluded: dict[UUID, set[UUID]] = {}
    members = await db.execute(
        select(ViewGroupMember.group_id, ViewGroupMember.asset_id, ViewGroupMember.role).where(
            ViewGroupMember.account_id == account_id
        )
    )
    for group_id, asset_id, role in members:
        by_role = old if role in AUTO_ROLES else added if role == ADDED else excluded
        by_role.setdefault(group_id, set()).add(asset_id)
    trash = set(
        await db.scalars(
            select(ViewPhotoTrash.asset_id).where(ViewPhotoTrash.account_id == account_id)
        )
    )
    in_group = {g: old.get(g, set()) | added.get(g, set()) for g in old.keys() | added.keys()}
    groups = {
        group.id: group
        for group in await db.scalars(
            select(ViewGroup).where(ViewGroup.account_id == account_id, ViewGroup.kind == KIND)
        )
    }
    dissolved = {group.id for group in groups.values() if group.dissolved}

    def work() -> tuple[list[dict[UUID, str]], list[float | None]]:
        pairs = uncut(all_pairs, trash, excluded, in_group, dissolved)
        built = build(pairs, places, rule)
        return built, closeness(built, pairs)

    # Millions of pairs on a large library: not on the event loop, the pages would wait for them.
    clusters, similarities = await asyncio.to_thread(work)
    continued = matched(clusters, old)
    added_anywhere = set().union(*added.values())

    await db.execute(
        delete(ViewGroupMember).where(
            ViewGroupMember.account_id == account_id, ViewGroupMember.role.in_(AUTO_ROLES)
        )
    )
    rows: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    kept: set[UUID] = set()
    for index, members_of in enumerate(clusters):
        if index in continued:
            group_id = continued[index]
            groups[group_id].similarity = similarities[index]
        else:
            group_id = uuid4()
            db.add(
                ViewGroup(
                    id=group_id,
                    account_id=account_id,
                    kind=KIND,
                    trash=False,
                    similarity=similarities[index],
                )
            )
        kept.add(group_id)
        out = excluded.get(group_id, set())
        rows.extend(
            {
                "group_id": group_id,
                "asset_id": asset_id,
                "account_id": account_id,
                "role": role,
                "created_at": now,
            }
            for asset_id, role in members_of.items()
            if asset_id not in added_anywhere and asset_id not in out
        )
    await db.flush()
    for start in range(0, len(rows), 5000):
        await db.execute(insert(ViewGroupMember), rows[start : start + 5000])
    # A group not found again stays while the user added photos to it.
    gone = [g for g in groups if g not in kept and g not in added and g not in dissolved]
    if gone:
        await db.execute(delete(ViewGroup).where(ViewGroup.id.in_(gone)))
    await db.commit()
    return {
        "groups": len(clusters),
        "in_groups": sum(len(c) for c in clusters),
        "largest": len(clusters[0]) if clusters else 0,
        "continued": len(continued),
        "removed": len(gone),
    }


# --- The job -------------------------------------------------------------------------------------


async def last_rebuild(db: AsyncSession, account_id: UUID) -> datetime | None:
    """When the groups were last rebuilt."""
    return await db.scalar(
        select(func.max(Job.finished_at)).where(
            Job.kind == JOB_KIND,
            Job.account_id == account_id,
            Job.status == "done",
            Job.progress["rebuilt"].as_boolean().is_(True),
        )
    )


async def is_due(db: AsyncSession, account_id: UUID) -> bool:
    """Whether the scheduler should start a job: new photos to search, groups older than the new
    neighbors (once `REBUILD_EVERY` has passed), or no rebuild for a day; not within
    `REBUILD_EVERY` of a failed job."""
    now = datetime.now(UTC)
    failed = await db.scalar(
        select(func.max(Job.finished_at)).where(
            Job.kind == JOB_KIND, Job.account_id == account_id, Job.status == "failed"
        )
    )
    # A failing job is not tried again every minute.
    if failed is not None and failed > now - REBUILD_EVERY:
        return False
    if await any_due(db, account_id):
        return True
    last = await last_rebuild(db, account_id)
    if last is None or last < now - REBUILD_AT_LEAST_EVERY:
        return True
    newer = await db.scalar(
        select(
            exists().where(ViewNeighbor.account_id == account_id, ViewNeighbor.computed_at > last)
        )
    )
    return bool(newer) and last < now - REBUILD_EVERY


async def run(
    db: AsyncSession,
    account_id: UUID,
    payload: dict[str, Any],
    on_progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    search_for: timedelta | None = None,
) -> dict[str, Any]:
    """One job: searches neighbors for a while, then, when none are left, rebuilds the groups
    (now if asked to, or once `REBUILD_EVERY` has passed since the last rebuild).

    Payload: "since" (ISO time) searches again the neighbors older than it (all the photos, by
    the button); "rebuild" rebuilds whatever the time since the last one; "reset" drops the groups
    first, with all that the user did to them (not the photos in the trash).
    """
    since = datetime.fromisoformat(payload["since"]) if payload.get("since") else None
    result: dict[str, Any] = await refresh_neighbors(
        db, account_id, since=since, search_for=search_for, on_progress=on_progress
    )
    result["rebuilt"] = False
    if result["left"]:
        return result
    last = await last_rebuild(db, account_id)
    if payload.get("rebuild") or last is None or last < datetime.now(UTC) - REBUILD_EVERY:
        if on_progress is not None:
            await on_progress({"stage": "groups"})
        if payload.get("reset"):
            await db.execute(
                delete(ViewGroup).where(ViewGroup.account_id == account_id, ViewGroup.kind == KIND)
            )
            await db.commit()
        result |= await rebuild(db, account_id, await rule_of(db, account_id))
        result["rebuilt"] = True
    return result


# --- What the pages show -------------------------------------------------------------------------


@dataclass(frozen=True)
class Summary:
    id: UUID
    name: str | None
    trash: bool
    photos: int
    without_location: int
    with_location: int
    # The photos with a location lie further apart than one spot.
    spread: bool
    similarity: float | None
    # Where most of the photos with a location lie; None with too few of them.
    spot: Spot | None = None

    @property
    def main_spot(self) -> bool:
        """Most of the photos with a location share one spot, so the group has a place."""
        return self.spot is not None and self.spot.photos / self.with_location >= SPOT_SHARE

    @property
    def ready(self) -> bool:
        """The photos without a location can get the one the others share."""
        return self.main_spot and self.without_location > 0


async def _main_spots(
    db: AsyncSession, account_id: UUID, group_id: UUID | None
) -> dict[UUID, Spot]:
    """Group -> its largest spot, for the groups with enough photos with a location."""
    latitude = func.round(cast(Asset.latitude, Numeric), SPOT_DECIMALS)
    longitude = func.round(cast(Asset.longitude, Numeric), SPOT_DECIMALS)
    query = (
        select(
            ViewGroup.id,
            func.avg(Asset.latitude).label("latitude"),
            func.avg(Asset.longitude).label("longitude"),
            func.count().label("photos"),
        )
        .join(ViewGroupMember, ViewGroupMember.group_id == ViewGroup.id)
        .join(Asset, Asset.id == ViewGroupMember.asset_id)
        .where(
            ViewGroup.account_id == account_id,
            ViewGroup.kind == KIND,
            ViewGroupMember.role != EXCLUDED,
            Asset.is_trashed.is_(False),
            located(),
        )
        .group_by(ViewGroup.id, latitude, longitude)
    )
    if group_id is not None:
        query = query.where(ViewGroup.id == group_id)
    cells: dict[UUID, list[Cell]] = {}
    for row in await db.execute(query):
        cells.setdefault(row.id, []).append((float(row.latitude), float(row.longitude), row.photos))
    return {
        group: spot_of(gathered(of_group)[0])
        for group, of_group in cells.items()
        if sum(c[2] for c in of_group) >= SPOT_MIN_PHOTOS
    }


def same_spot(found: list[Summary], group_id: UUID) -> list[Summary]:
    """The other groups whose main spot is that of the group, the largest first."""
    own = next((s.spot for s in found if s.id == group_id), None)
    if own is None:
        return []
    return sorted(
        (
            s
            for s in found
            if s.id != group_id
            and s.spot is not None
            and not s.trash
            and distance_m(own.latitude, own.longitude, s.spot.latitude, s.spot.longitude)
            <= similar.JOIN_M
        ),
        key=lambda s: -s.photos,
    )


async def summaries(
    db: AsyncSession, account_id: UUID, group_id: UUID | None = None
) -> list[Summary]:
    """The groups of the account (or just that one): those named by the user first, then the
    largest."""
    place = located()
    query = (
        select(
            ViewGroup.id,
            ViewGroup.name,
            ViewGroup.trash,
            ViewGroup.similarity,
            func.count().label("photos"),
            func.count().filter(place).label("with_location"),
            func.min(Asset.latitude).filter(place).label("south"),
            func.max(Asset.latitude).filter(place).label("north"),
            func.min(Asset.longitude).filter(place).label("west"),
            func.max(Asset.longitude).filter(place).label("east"),
        )
        .join(ViewGroupMember, ViewGroupMember.group_id == ViewGroup.id)
        .join(Asset, Asset.id == ViewGroupMember.asset_id)
        .where(
            ViewGroup.account_id == account_id,
            ViewGroup.kind == KIND,
            ViewGroupMember.role != EXCLUDED,
            Asset.is_trashed.is_(False),
        )
        .group_by(ViewGroup.id)
    )
    if group_id is not None:
        query = query.where(ViewGroup.id == group_id)
    rows = await db.execute(query)
    spots = await _main_spots(db, account_id, group_id)
    found = [
        Summary(
            id=row.id,
            name=row.name,
            trash=row.trash,
            photos=row.photos,
            without_location=row.photos - row.with_location,
            with_location=row.with_location,
            spread=row.with_location > 1
            and distance_m(row.south, row.west, row.north, row.east) > similar.JOIN_M,
            similarity=row.similarity,
            spot=spots.get(row.id),
        )
        for row in rows
    ]
    found.sort(key=lambda s: (s.name is None, -s.photos, s.id))
    return found


async def covers(db: AsyncSession, group_ids: list[UUID]) -> dict[UUID, tuple[UUID, str | None]]:
    """Group -> the photo on its cover and the version of its thumbnails: the latest of its core
    photos, or of the others when it has none left."""
    rows = await db.execute(
        select(ViewGroupMember.group_id, Asset.id, Asset.thumbhash)
        .join(Asset, Asset.id == ViewGroupMember.asset_id)
        .where(
            ViewGroupMember.group_id.in_(group_ids),
            ViewGroupMember.role != EXCLUDED,
            Asset.is_trashed.is_(False),
        )
        .ext(distinct_on(ViewGroupMember.group_id))
        .order_by(
            ViewGroupMember.group_id,
            (ViewGroupMember.role == CORE).desc(),
            Asset.local_taken_at.desc(),
            Asset.id,
        )
    )
    return {group_id: (asset_id, version) for group_id, asset_id, version in rows}


async def photos_of(db: AsyncSession, group_id: UUID) -> list[Asset]:
    """All the photos of the group, oldest first."""
    found = await db.scalars(
        select(Asset)
        .join(ViewGroupMember, ViewGroupMember.asset_id == Asset.id)
        .where(
            ViewGroupMember.group_id == group_id,
            ViewGroupMember.role != EXCLUDED,
            Asset.is_trashed.is_(False),
        )
        .order_by(Asset.local_taken_at, Asset.id)
    )
    return list(found)


async def parts(
    db: AsyncSession, group_id: UUID, rule: Rule, level: int
) -> tuple[float, list[list[UUID]]]:
    """The similarity of this level of strictness and the scenes of the group at it; only a look
    at the photos: nothing is stored and the group stays as it is."""
    similarity = round(rule.similarity + level * PART_STEP, 3)
    rows = await db.execute(_GROUP_PAIRS, {"group_id": group_id, "similarity": similarity})
    return similarity, parts_of([(a, b, float(s)) for a, b, s in rows], rule)


async def photo_closeness(db: AsyncSession, group_id: UUID) -> dict[UUID, float]:
    """Photo -> its mean similarity to the photos of the group among its neighbors."""
    rows = await db.execute(_PHOTO_CLOSENESS, {"group_id": group_id})
    return {row.asset_id: round(float(row.similarity), 3) for row in rows}


def center_of(closeness_of: dict[UUID, float]) -> list[UUID]:
    """The center of a group: the photos closest to the rest of it, closest first. More telling
    than the core of the rule, which nearly every photo of a group of shots passes."""
    ordered = sorted(closeness_of, key=lambda a: (-closeness_of[a], a))
    return ordered[: max(CENTER_MIN_PHOTOS, ceil(len(ordered) * CENTER_SHARE))]


async def dissolve(db: AsyncSession, group: ViewGroup) -> None:
    """Takes the group apart: its photos are out of it and link nothing among them."""
    group.dissolved = True
    await db.execute(
        update(ViewGroupMember).where(ViewGroupMember.group_id == group.id).values(role=EXCLUDED)
    )
    await db.commit()


async def bring_back(db: AsyncSession, group: ViewGroup) -> None:
    """Undoes `dissolve`: its photos in no other group are back, for the next rebuild to find it
    again, with its name. What the user took out before it was dissolved comes back too."""
    group.dissolved = False
    taken = (
        select(ViewGroupMember.asset_id).where(ViewGroupMember.role != EXCLUDED).scalar_subquery()
    )
    await db.execute(
        delete(ViewGroupMember).where(
            ViewGroupMember.group_id == group.id, ViewGroupMember.asset_id.in_(taken)
        )
    )
    await db.execute(
        update(ViewGroupMember).where(ViewGroupMember.group_id == group.id).values(role=ATTACHED)
    )
    await db.commit()


async def dissolved_summaries(db: AsyncSession, account_id: UUID) -> list[Summary]:
    """The groups the user took apart, the last ones first."""
    rows = await db.execute(
        select(ViewGroup.id, ViewGroup.name, ViewGroup.trash, func.count().label("photos"))
        .join(ViewGroupMember, ViewGroupMember.group_id == ViewGroup.id)
        .where(ViewGroup.account_id == account_id, ViewGroup.dissolved)
        .group_by(ViewGroup.id)
        .order_by(ViewGroup.updated_at.desc())
    )
    return [Summary(r.id, r.name, r.trash, r.photos, 0, 0, False, None) for r in rows]


async def excluded_cover(
    db: AsyncSession, group_ids: list[UUID]
) -> dict[UUID, tuple[UUID, str | None]]:
    """As `covers`, for groups whose photos are all taken out."""
    rows = await db.execute(
        select(ViewGroupMember.group_id, Asset.id, Asset.thumbhash)
        .join(Asset, Asset.id == ViewGroupMember.asset_id)
        .where(ViewGroupMember.group_id.in_(group_ids), Asset.is_trashed.is_(False))
        .ext(distinct_on(ViewGroupMember.group_id))
        .order_by(ViewGroupMember.group_id, Asset.local_taken_at.desc(), Asset.id)
    )
    return {group_id: (asset_id, version) for group_id, asset_id, version in rows}


async def excluded_of(db: AsyncSession, group_id: UUID) -> list[Asset]:
    """The photos the user took out of the group, oldest first."""
    found = await db.scalars(
        select(Asset)
        .join(ViewGroupMember, ViewGroupMember.asset_id == Asset.id)
        .where(
            ViewGroupMember.group_id == group_id,
            ViewGroupMember.role == EXCLUDED,
            Asset.is_trashed.is_(False),
        )
        .order_by(Asset.local_taken_at, Asset.id)
    )
    return list(found)


async def near(db: AsyncSession, group_id: UUID, rule: Rule) -> list[Asset]:
    """Photos in no group that are almost close to a photo of the group: where its border runs.
    The most similar first."""
    rows = await db.execute(
        _NEAR,
        {
            "group_id": group_id,
            "similarity": rule.similarity - NEAR_MARGIN,
            "limit": NEAR_LIMIT,
        },
    )
    order = [row.asset_id for row in rows]
    found = {a.id: a for a in await db.scalars(select(Asset).where(Asset.id.in_(order)))}
    return [found[asset_id] for asset_id in order if asset_id in found]


async def exclude(db: AsyncSession, group_id: UUID, asset_ids: list[UUID]) -> None:
    """Takes photos out of the group; rebuilds keep them out."""
    await db.execute(
        update(ViewGroupMember)
        .where(ViewGroupMember.group_id == group_id, ViewGroupMember.asset_id.in_(asset_ids))
        .values(role=EXCLUDED)
    )
    await db.commit()


async def include(
    db: AsyncSession, group_id: UUID, account_id: UUID, asset_ids: list[UUID]
) -> None:
    """Puts photos of the account into the group by hand, out of any other group."""
    own = list(
        await db.scalars(
            select(Asset.id).where(Asset.id.in_(asset_ids), Asset.account_id == account_id)
        )
    )
    if not own:
        return
    await db.execute(
        delete(ViewGroupMember).where(
            ViewGroupMember.asset_id.in_(own),
            or_(ViewGroupMember.role != EXCLUDED, ViewGroupMember.group_id == group_id),
        )
    )
    await db.execute(
        insert(ViewGroupMember),
        [
            {
                "group_id": group_id,
                "asset_id": asset_id,
                "account_id": account_id,
                "role": ADDED,
                "created_at": datetime.now(UTC),
            }
            for asset_id in own
        ],
    )
    await db.commit()


async def trash_photos(db: AsyncSession, account_id: UUID, asset_ids: list[UUID]) -> None:
    """Puts photos of the account into the trash, and out of their groups at once."""
    own = list(
        await db.scalars(
            select(Asset.id).where(Asset.id.in_(asset_ids), Asset.account_id == account_id)
        )
    )
    if not own:
        return
    await db.execute(
        postgresql_insert(ViewPhotoTrash)
        .values([{"asset_id": a, "account_id": account_id, "created_at": utcnow()} for a in own])
        .on_conflict_do_nothing()
    )
    await db.execute(delete(ViewGroupMember).where(ViewGroupMember.asset_id.in_(own)))
    await db.commit()


async def restore_photos(db: AsyncSession, account_id: UUID, asset_ids: list[UUID]) -> None:
    await db.execute(
        delete(ViewPhotoTrash).where(
            ViewPhotoTrash.account_id == account_id, ViewPhotoTrash.asset_id.in_(asset_ids)
        )
    )
    await db.commit()


async def of_photo(
    db: AsyncSession, account_id: UUID, asset_id: UUID
) -> tuple[ViewGroup | None, bool]:
    """The group of the photo, and whether it is marked as showing nothing of the place: by
    itself or with its group."""
    group = await db.scalar(
        select(ViewGroup)
        .join(ViewGroupMember, ViewGroupMember.group_id == ViewGroup.id)
        .where(
            ViewGroupMember.asset_id == asset_id,
            ViewGroupMember.role != EXCLUDED,
            ViewGroup.account_id == account_id,
            ViewGroup.dissolved.is_(False),
        )
    )
    marked = await db.scalar(
        select(
            exists().where(
                ViewPhotoTrash.asset_id == asset_id, ViewPhotoTrash.account_id == account_id
            )
        )
    )
    return group, bool(marked) or (group is not None and group.trash)


async def set_in_app(db: AsyncSession, asset_ids: list[UUID]) -> set[UUID]:
    """Those of the photos whose location was written by this app."""
    rows = await db.scalars(
        select(LocationChange.asset_id)
        .where(LocationChange.asset_id.in_(asset_ids), LocationChange.status == "applied")
        .distinct()
    )
    return set(rows)


async def trashed_photos(db: AsyncSession, account_id: UUID, limit: int) -> tuple[int, list[Asset]]:
    """How many photos are in the trash, and the ones put there last."""
    total = await db.scalar(
        select(func.count())
        .select_from(ViewPhotoTrash)
        .where(ViewPhotoTrash.account_id == account_id)
    )
    found = await db.scalars(
        select(Asset)
        .join(ViewPhotoTrash, ViewPhotoTrash.asset_id == Asset.id)
        .where(ViewPhotoTrash.account_id == account_id)
        .order_by(ViewPhotoTrash.created_at.desc(), Asset.id)
        .limit(limit)
    )
    return total or 0, list(found)


async def progress_counts(db: AsyncSession, account_id: UUID) -> dict[str, int]:
    """How far the search of neighbors is: photos with a vector, and those already searched."""
    vectors = await db.scalar(
        select(func.count())
        .select_from(Embedding)
        .where(
            Embedding.account_id == account_id,
            Embedding.module_id == similar.MODULE_ID,
            Embedding.region.is_(False),
        )
    )
    searched = await db.scalar(
        select(func.count()).select_from(ViewNeighbor).where(ViewNeighbor.account_id == account_id)
    )
    return {"vectors": vectors or 0, "searched": searched or 0}
