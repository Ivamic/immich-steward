# SPDX-License-Identifier: AGPL-3.0-or-later
"""M3: similar photos from the user's own library (MegaLoc; D-104…D-108).

Workers compute the vectors of the photos (`steward.embeddings`); the search runs here whenever
the suggestions are shown, so it always sees the library as it is now: new photos with a location
and the locations set since. The most similar photos with a location are grouped by place; each
group is a candidate at the spot of its most similar photo.
"""

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from steward.config import Settings
from steward.models import EMBEDDING_DIM, Embedding, ModuleRun
from steward.modules.base import Candidate
from steward.modules.time_neighbors import distance_m

MODULE_ID = "similar"
# Nearest by the sign bits first, then exact (D-108): 400 keeps the top 50 as the exact search.
POOL = 400
NEIGHBORS = 30
# Photos within this distance of the most similar one of a group belong to it.
JOIN_M = 1000.0
MIN_RADIUS_M = 100.0
MAX_CANDIDATES = 5
# Thumbnails shown per candidate.
MAX_EVIDENCE = 6

# Similarity of the best photo of a candidate -> how often such a candidate is right within 1 km.
# Measured on 15 516 photos with camera GPS of a family library (2026-10-21, photos taken within
# 2-24 h of the query excluded): below ~0.15 nearly never, from ~0.45 nine times out of ten.
CALIBRATION = (
    (0.10, 0.10),
    (0.15, 0.20),
    (0.18, 0.40),
    (0.22, 0.55),
    (0.27, 0.70),
    (0.35, 0.80),
    (0.45, 0.88),
    (0.55, 0.97),
)

# The vector is sent as text; Postgres needs its type to pick the operators and the index.
_QUERY = f"CAST(:query AS halfvec({EMBEDDING_DIM}))"
_SEARCH = text(
    f"""
    SELECT near.asset_id, -(near.vector <#> {_QUERY}) AS similarity,
        asset.latitude, asset.longitude, asset.local_taken_at, asset.original_file_name,
        EXISTS (
            SELECT 1 FROM location_change
            WHERE location_change.asset_id = asset.id AND location_change.status = 'applied'
        ) AS estimated,
        asset.thumbhash
    FROM (
        SELECT asset_id, vector FROM embedding
        WHERE located AND account_id = :account_id AND module_id = :module_id
            AND asset_id <> :asset_id
        ORDER BY binary_quantize(vector)::bit({EMBEDDING_DIM}) <~> binary_quantize({_QUERY})
        LIMIT :pool
    ) AS near
    JOIN asset ON asset.id = near.asset_id
    ORDER BY near.vector <#> {_QUERY}
    LIMIT :limit
    """
).bindparams(bindparam("query", type_=Embedding.vector.type))


@dataclass(frozen=True)
class Neighbor:
    asset_id: UUID
    similarity: float
    latitude: float
    longitude: float
    local_taken_at: datetime
    file_name: str
    # The location was written by this app, not recorded by a camera.
    estimated: bool
    # Changes with the thumbnails (`AssetItem.version`).
    version: str | None = None


def calibrated(similarity: float) -> float:
    """Chance that a candidate whose best photo is this similar is right (`CALIBRATION`)."""
    points = [s for s, _ in CALIBRATION]
    if similarity <= points[0]:
        return CALIBRATION[0][1]
    if similarity >= points[-1]:
        return CALIBRATION[-1][1]
    i = bisect.bisect_right(points, similarity)
    (s0, p0), (s1, p1) = CALIBRATION[i - 1], CALIBRATION[i]
    return p0 + (p1 - p0) * (similarity - s0) / (s1 - s0)


async def neighbors(
    db: AsyncSession, run: ModuleRun, account_id: UUID, include_estimated: bool
) -> list[Neighbor]:
    """The photos with a location most similar to the photo (or the part of it) of the run."""
    query = await db.scalar(select(Embedding.vector).where(Embedding.run_id == run.id))
    if query is None:
        return []
    return await search(db, query, account_id, run.asset_id, include_estimated)


async def search(
    db: AsyncSession,
    query: Any,
    account_id: UUID,
    asset_id: UUID,
    include_estimated: bool,
    limit: int = NEIGHBORS,
) -> list[Neighbor]:
    """The photos with a location of the account most similar to the vector, but the photo
    itself; most similar first."""
    # Filtering by account inside the index scan needs the iterative scan (pgvector 0.8).
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {POOL}"))
    await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    rows = await db.execute(
        _SEARCH,
        {
            "query": query,
            "account_id": account_id,
            "module_id": MODULE_ID,
            "asset_id": asset_id,
            "pool": POOL,
            "limit": limit,
        },
    )
    found = [Neighbor(*row) for row in rows]
    return [n for n in found if include_estimated or not n.estimated]


def candidates(found: list[Neighbor], taken_at: datetime, settings: Settings) -> list[Candidate]:
    """Groups the neighbors by place, best first; drops the groups below the display minimum."""
    groups: list[list[Neighbor]] = []
    for neighbor in found:  # most similar first
        for group in groups:
            seed = group[0]
            if distance_m(seed.latitude, seed.longitude, neighbor.latitude, neighbor.longitude) <= (
                JOIN_M
            ):
                group.append(neighbor)
                break
        else:
            groups.append([neighbor])

    result = []
    for group in groups:
        score = calibrated(group[0].similarity)
        if score < settings.similar_min_confidence:
            continue
        seed = group[0]
        spread = max(
            distance_m(seed.latitude, seed.longitude, n.latitude, n.longitude) for n in group
        )
        result.append(
            Candidate(
                latitude=seed.latitude,
                longitude=seed.longitude,
                score=round(score, 4),
                radius_m=round(max(spread, MIN_RADIUS_M)),
                kind="similar",
                evidence={"neighbors": [_evidence(n, taken_at) for n in group[:MAX_EVIDENCE]]},
            )
        )
    return result[:MAX_CANDIDATES]


def _evidence(neighbor: Neighbor, taken_at: datetime) -> dict[str, object]:
    return {
        "asset_id": str(neighbor.asset_id),
        "file_name": neighbor.file_name,
        "similarity": round(neighbor.similarity, 3),
        "local_taken_at": neighbor.local_taken_at.isoformat(),
        "delta_s": (neighbor.local_taken_at - taken_at).total_seconds(),
        "estimated": neighbor.estimated,
        "version": neighbor.version,
    }


async def suggest(
    db: AsyncSession, run: ModuleRun, account_id: UUID, taken_at: datetime, settings: Settings
) -> list[Candidate]:
    found = await neighbors(db, run, account_id, settings.similar_include_estimated)
    return candidates(found, taken_at, settings)
