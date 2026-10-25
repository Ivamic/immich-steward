# SPDX-License-Identifier: AGPL-3.0-or-later
"""Suggestions for several photos chosen together in the gallery (D-149).

Made only from what is already known, so that they come at once for any number of photos: the
locations some of the chosen photos already have, the located photos just before and after them in
time, and the confident results of the worker modules that already ran on them. Nothing is run.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.config import Settings
from steward.gallery import CAMERA_SEPARATOR
from steward.models import Asset, LocationChange, ModuleRun
from steward.modules import REMOTE_MODULES, similar
from steward.modules.base import Candidate, MarkerShape, ModuleResult, TrackPoint
from steward.modules.time_neighbors import (
    MAX_TRACK_POINTS,
    TimeNeighbors,
    camera_label,
    camera_value,
    distance_m,
    is_scanner,
    merge,
    nearest,
    single,
)
from steward.worker_queue import whole_photo

# The chosen photos that already have a location: "the truth is somewhere near".
SELECTION_ID = "selection"
SELECTION_COLOR = "#8250df"
SELECTION_SHAPE: MarkerShape = "circle"

# Locations closer than this are one suggestion.
MERGE_DISTANCE_M = 100.0
BASE_RADIUS_M = 50.0
# Photos shown under one suggestion.
MAX_EVIDENCE = 6
# Similar photos are searched now (D-105): only for this many of the chosen photos.
MAX_SIMILAR_SEARCHES = 40


@dataclass
class Block:
    module: str
    result: ModuleResult
    color: str = ""
    shape: MarkerShape = "circle"
    version: str = ""


@dataclass
class _Cluster:
    best: Candidate
    radius_m: float
    photos: set[UUID] = field(default_factory=set)
    neighbors: dict[str, dict[str, Any]] = field(default_factory=dict)


async def suggest(
    db: AsyncSession,
    account_id: UUID,
    assets: list[Asset],
    settings: Settings,
    confident: Callable[[str, float], bool],
) -> list[Block]:
    """Suggestion blocks for the chosen photos, in display order; `confident(module, score)` tells
    the results of a worker module worth showing."""
    neighbors = TimeNeighbors()
    blocks = [
        Block(SELECTION_ID, await _located(db, assets), SELECTION_COLOR, SELECTION_SHAPE),
        Block(
            neighbors.id,
            await _time_neighbors(db, account_id, assets, settings),
            neighbors.color,
            neighbors.shape,
            neighbors.version,
        ),
    ]
    for remote in REMOTE_MODULES.values():
        result = await _remote(db, account_id, assets, remote.id, settings, confident)
        blocks.append(Block(remote.id, result, remote.color, remote.shape))
    return blocks


async def _located(db: AsyncSession, assets: list[Asset]) -> ModuleResult:
    located = [a for a in assets if a.latitude is not None and a.longitude is not None]
    if not located:
        return ModuleResult(note="none_located")
    estimated = await _estimated(db, [a.id for a in located])
    clusters: list[_Cluster] = []
    for asset in located:
        point = _point(asset, 0.0, estimated)
        candidate = Candidate(
            latitude=asset.latitude,  # type: ignore[arg-type]
            longitude=asset.longitude,  # type: ignore[arg-type]
            score=0.0,
            radius_m=BASE_RADIUS_M,
            kind="selected",
        )
        _add(clusters, candidate, asset.id, [point], MERGE_DISTANCE_M)
    candidates = [
        replace(
            cluster.best,
            score=len(cluster.photos) / len(located),
            radius_m=cluster.radius_m,
            evidence=_evidence(cluster),
        )
        for cluster in clusters
    ]
    return ModuleResult(candidates=sorted(candidates, key=lambda c: -c.score))


async def _time_neighbors(
    db: AsyncSession, account_id: UUID, assets: list[Asset], settings: Settings
) -> ModuleResult:
    """The located photos just before the first chosen photo and just after the last one."""
    first = min(a.local_taken_at for a in assets)
    last = max(a.local_taken_at for a in assets)
    window = timedelta(hours=settings.time_neighbors_window_hours)
    chosen = {a.id for a in assets}
    edge = func.greatest(
        func.extract("epoch", first - Asset.local_taken_at),
        func.extract("epoch", Asset.local_taken_at - last),
        0,
    )
    rows = (
        await db.scalars(
            select(Asset)
            .where(
                Asset.account_id == account_id,
                Asset.is_trashed.is_(False),
                Asset.latitude.is_not(None),
                Asset.longitude.is_not(None),
                Asset.id.not_in(chosen),
                Asset.local_taken_at.between(first - window, last + window),
            )
            .order_by(edge)
            .limit(MAX_TRACK_POINTS)
        )
    ).all()
    found = [n for n in rows if not is_scanner(n.camera_make, n.camera_model)]
    if not found:
        return ModuleResult(note="no_neighbors")
    estimated = await _estimated(db, [n.id for n in found])
    cameras = {camera_value(a.camera_make, a.camera_model) for a in assets}
    track = sorted(
        (_point(n, _delta(n, first, last), estimated, cameras) for n in found),
        key=lambda p: p.delta_s,
    )
    before = nearest([p for p in track if p.delta_s <= 0])
    after = nearest([p for p in track if p.delta_s > 0])
    track = [
        replace(p, role="before" if p is before else "after" if p is after else None) for p in track
    ]
    candidates = [single(p) for p in (before, after) if p is not None]
    return ModuleResult(candidates=merge(candidates), track=track)


async def _remote(
    db: AsyncSession,
    account_id: UUID,
    assets: list[Asset],
    module_id: str,
    settings: Settings,
    confident: Callable[[str, float], bool],
) -> ModuleResult:
    """The confident results of the module's latest finished runs on the chosen photos, the same
    place for several photos as one suggestion."""
    by_id = {a.id: a for a in assets}
    runs = await db.scalars(
        select(ModuleRun)
        .where(
            ModuleRun.asset_id.in_(by_id),
            ModuleRun.module_id == module_id,
            whole_photo(),
        )
        .order_by(ModuleRun.created_at.desc())
    )
    latest: dict[UUID, ModuleRun] = {}
    for run in runs:
        latest.setdefault(run.asset_id, run)
    clusters: list[_Cluster] = []
    searches = 0
    for run in latest.values():
        if run.status != "done":
            continue
        asset = by_id[run.asset_id]
        if module_id == similar.MODULE_ID:
            if searches >= MAX_SIMILAR_SEARCHES:
                continue
            searches += 1
            found = [
                vars(c)
                for c in await similar.suggest(db, run, account_id, asset.local_taken_at, settings)
            ]
        else:
            found = run.candidates
        for item in found:
            if not confident(module_id, item["score"]):
                continue
            candidate = Candidate(**item)
            radius = max(candidate.radius_m or 0.0, MERGE_DISTANCE_M)
            _add(clusters, candidate, asset.id, candidate.evidence.get("neighbors", []), radius)
    candidates = [
        replace(cluster.best, radius_m=cluster.radius_m, evidence=_evidence(cluster))
        for cluster in sorted(clusters, key=lambda c: (-len(c.photos), -c.best.score))
    ]
    return ModuleResult(candidates=candidates)


def _add(
    clusters: list[_Cluster],
    candidate: Candidate,
    asset_id: UUID,
    neighbors: list[Any],
    merge_m: float,
) -> None:
    """Puts the candidate of a photo into the first cluster it is close to, or a new one."""
    for cluster in clusters:
        distance = distance_m(
            cluster.best.latitude, cluster.best.longitude, candidate.latitude, candidate.longitude
        )
        if distance <= max(merge_m, min(cluster.radius_m, candidate.radius_m or merge_m)):
            if candidate.score > cluster.best.score:
                cluster.best = candidate
            cluster.radius_m = max(cluster.radius_m, distance + BASE_RADIUS_M)
            break
    else:
        cluster = _Cluster(best=candidate, radius_m=candidate.radius_m or BASE_RADIUS_M)
        clusters.append(cluster)
    cluster.photos.add(asset_id)
    for neighbor in neighbors:
        item = neighbor if isinstance(neighbor, dict) else _neighbor(neighbor)
        cluster.neighbors.setdefault(item["asset_id"], item)


def _evidence(cluster: _Cluster) -> dict[str, Any]:
    neighbors = list(cluster.neighbors.values())[:MAX_EVIDENCE]
    return {**cluster.best.evidence, "neighbors": neighbors, "photos": len(cluster.photos)}


def _delta(asset: Asset, first: datetime, last: datetime) -> float:
    """Seconds from the chosen photos: before the first one negative, after the last one
    positive, between them 0."""
    if asset.local_taken_at < first:
        return (asset.local_taken_at - first).total_seconds()
    if asset.local_taken_at > last:
        return (asset.local_taken_at - last).total_seconds()
    return 0.0


def _point(
    asset: Asset, delta_s: float, estimated: set[UUID], cameras: set[str] | None = None
) -> TrackPoint:
    camera = camera_value(asset.camera_make, asset.camera_model)
    return TrackPoint(
        asset_id=asset.id,
        latitude=asset.latitude,  # type: ignore[arg-type]
        longitude=asset.longitude,  # type: ignore[arg-type]
        local_taken_at=asset.local_taken_at,
        delta_s=delta_s,
        file_name=asset.original_file_name,
        camera=camera_label(camera),
        same_camera=cameras is None or (camera in cameras and camera != CAMERA_SEPARATOR),
        estimated=asset.id in estimated,
        version=asset.thumbhash,
    )


def _neighbor(point: TrackPoint) -> dict[str, Any]:
    return {
        "asset_id": str(point.asset_id),
        "file_name": point.file_name,
        "delta_s": point.delta_s,
        "same_camera": point.same_camera,
        "estimated": point.estimated,
        "version": point.version,
        "local_taken_at": point.local_taken_at.isoformat(),
    }


async def _estimated(db: AsyncSession, ids: list[UUID]) -> set[UUID]:
    """Of these photos, those whose location this app wrote."""
    return set(
        await db.scalars(
            select(LocationChange.asset_id).where(
                LocationChange.asset_id.in_(ids), LocationChange.status == "applied"
            )
        )
    )
