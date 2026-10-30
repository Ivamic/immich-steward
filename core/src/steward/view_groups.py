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
A rebuild keeps the groups whose photos it finds again: their id, name, trash mark and the photos
added or taken out by the user.
"""

from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Select,
    bindparam,
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
from sqlalchemy.ext.asyncio import AsyncSession

from steward import account_settings
from steward.embeddings import located
from steward.models import (
    EMBEDDING_DIM,
    Asset,
    Embedding,
    Job,
    ViewGroup,
    ViewGroupMember,
    ViewNeighbor,
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

# Photos this much less similar than a group asks for are shown next to it.
NEAR_MARGIN = 0.1
NEAR_LIMIT = 60

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
    clusters = cluster(((a, b, float(s)) for a, b, s in close), rule.core_neighbors)

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
    groups = {
        group.id: group
        for group in await db.scalars(
            select(ViewGroup).where(ViewGroup.account_id == account_id, ViewGroup.kind == KIND)
        )
    }
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
        else:
            group_id = uuid4()
            db.add(ViewGroup(id=group_id, account_id=account_id, kind=KIND, trash=False))
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
    gone = [group_id for group_id in groups if group_id not in kept and group_id not in added]
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
    the button); "rebuild" rebuilds whatever the time since the last one.
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
    # The photos with a location lie further apart than one spot.
    spread: bool


async def summaries(db: AsyncSession, account_id: UUID) -> list[Summary]:
    """The groups of the account: those named by the user first, then the largest."""
    place = located()
    rows = await db.execute(
        select(
            ViewGroup.id,
            ViewGroup.name,
            ViewGroup.trash,
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
    found = [
        Summary(
            id=row.id,
            name=row.name,
            trash=row.trash,
            photos=row.photos,
            without_location=row.photos - row.with_location,
            spread=row.with_location > 1
            and distance_m(row.south, row.west, row.north, row.east) > similar.JOIN_M,
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
