# SPDX-License-Identifier: AGPL-3.0-or-later
"""M1: located photos taken shortly before and after the asset.

Times are compared by the camera clock (`local_taken_at`, D-045): most old cameras store no time
zone, and one camera's clock is consistent with itself. Other cameras count with a lower weight,
since their clocks may be off or set to another zone.
"""

import math
import re
from collections import Counter
from datetime import timedelta
from typing import Literal

from sqlalchemy import func, select

from steward.gallery import CAMERA_SEPARATOR
from steward.models import Asset, LocationChange
from steward.modules.base import (
    CameraCount,
    Candidate,
    MarkerShape,
    ModuleContext,
    ModuleResult,
    TrackPoint,
)

# Scanned photos carry the scan date, not the capture date.
SCANNER = re.compile(r"scan|epson|perfection|coolscan|plustek|fujitsu fi-", re.IGNORECASE)

# Score halves roughly every 40 minutes: 5 min ~ 0.92, 1 h ~ 0.37, 3 h ~ 0.05.
SCORE_TIME_S = 3600.0
OTHER_CAMERA_FACTOR = 0.6
# Error radius: a base plus walking speed times the time gap, capped.
BASE_RADIUS_M = 50.0
SPEED_M_S = 1.0
MAX_RADIUS_M = 20_000.0
# Faster than this between "before" and "after" means a wrong clock (or a plane): no interpolation.
MAX_SPEED_M_S = 70.0
# Candidates closer than this are merged.
MERGE_DISTANCE_M = 100.0
MAX_TRACK_POINTS = 200


class TimeNeighbors:
    id = "time_neighbors"
    version = "1"
    color = "#0969da"
    shape: MarkerShape = "circle"
    privacy: Literal["local", "external"] = "local"

    async def run(self, ctx: ModuleContext) -> ModuleResult:
        asset = ctx.asset
        if is_scanner(asset.camera_make, asset.camera_model):
            return ModuleResult(note="scanner")

        window = timedelta(hours=ctx.settings.time_neighbors_window_hours)
        rows = (
            await ctx.db.scalars(
                select(Asset)
                .where(
                    Asset.account_id == ctx.account.id,
                    Asset.is_trashed.is_(False),
                    Asset.latitude.is_not(None),
                    Asset.longitude.is_not(None),
                    Asset.id != asset.id,
                    Asset.local_taken_at.between(
                        asset.local_taken_at - window, asset.local_taken_at + window
                    ),
                )
                .order_by(
                    func.abs(func.extract("epoch", Asset.local_taken_at - asset.local_taken_at))
                )
                .limit(MAX_TRACK_POINTS)
            )
        ).all()
        found = [n for n in rows if not is_scanner(n.camera_make, n.camera_model)]
        own = camera_value(asset.camera_make, asset.camera_model)
        has_own = any((asset.camera_make, asset.camera_model))

        def excluded(value: str) -> bool:
            if ctx.same_camera_only and has_own:
                return value != own
            return value in ctx.exclude_cameras

        counts = Counter(camera_value(n.camera_make, n.camera_model) for n in found)
        cameras = [
            CameraCount(
                value=value,
                label=camera_label(value),
                count=count,
                same_camera=value == own and has_own,
                excluded=excluded(value),
            )
            # This camera first, then by number of photos.
            for value, count in sorted(counts.items(), key=lambda vc: (vc[0] != own, -vc[1]))
        ]
        neighbors = [n for n in found if not excluded(camera_value(n.camera_make, n.camera_model))]
        if not neighbors:
            return ModuleResult(note="no_neighbors", cameras=cameras)

        estimated = set(
            await ctx.db.scalars(
                select(LocationChange.asset_id).where(
                    LocationChange.asset_id.in_([n.id for n in neighbors]),
                    LocationChange.status == "applied",
                )
            )
        )
        camera = (asset.camera_make, asset.camera_model)
        has_camera = any(camera)
        track = sorted(
            (
                TrackPoint(
                    asset_id=n.id,
                    latitude=n.latitude,  # type: ignore[arg-type]
                    longitude=n.longitude,  # type: ignore[arg-type]
                    local_taken_at=n.local_taken_at,
                    delta_s=(n.local_taken_at - asset.local_taken_at).total_seconds(),
                    file_name=n.original_file_name,
                    camera=camera_label(camera_value(n.camera_make, n.camera_model)),
                    same_camera=has_camera and (n.camera_make, n.camera_model) == camera,
                    estimated=n.id in estimated,
                )
                for n in neighbors
            ),
            key=lambda p: p.delta_s,
        )

        before = _nearest([p for p in track if p.delta_s <= 0])
        after = _nearest([p for p in track if p.delta_s > 0])
        track = [
            _with_role(p, "before" if p is before else "after" if p is after else None)
            for p in track
        ]
        candidates = [_single(p) for p in (before, after) if p is not None]
        between = _between(before, after) if before and after else None
        if between:
            candidates.append(between)
        return ModuleResult(candidates=_merge(candidates), track=track, cameras=cameras)


def camera_value(make: str | None, model: str | None) -> str:
    return f"{make or ''}{CAMERA_SEPARATOR}{model or ''}"


def camera_label(value: str) -> str:
    make, _, model = value.partition(CAMERA_SEPARATOR)
    # Models often repeat the make ("Canon" + "Canon EOS 600D").
    if make and model.lower().startswith(make.lower()):
        return model
    return " ".join(part for part in (make, model) if part)


def is_scanner(make: str | None, model: str | None) -> bool:
    return bool(SCANNER.search(f"{make or ''} {model or ''}"))


def _nearest(points: list[TrackPoint]) -> TrackPoint | None:
    """The closest point in time, preferring the same camera."""
    same = [p for p in points if p.same_camera]
    pool = same or points
    return min(pool, key=lambda p: abs(p.delta_s), default=None)


def _with_role(point: TrackPoint, role: str | None) -> TrackPoint:
    if role is None:
        return point
    return TrackPoint(**{**point.__dict__, "role": role})


def _time_score(seconds: float) -> float:
    return math.exp(-abs(seconds) / SCORE_TIME_S)


def _camera_factor(*points: TrackPoint) -> float:
    return 1.0 if all(p.same_camera for p in points) else OTHER_CAMERA_FACTOR


def _radius(seconds: float) -> float:
    return min(BASE_RADIUS_M + SPEED_M_S * abs(seconds), MAX_RADIUS_M)


def _evidence(*points: TrackPoint) -> dict[str, object]:
    return {
        "neighbors": [
            {
                "asset_id": str(p.asset_id),
                "file_name": p.file_name,
                "delta_s": p.delta_s,
                "same_camera": p.same_camera,
                "estimated": p.estimated,
            }
            for p in points
        ]
    }


def _single(point: TrackPoint) -> Candidate:
    return Candidate(
        latitude=point.latitude,
        longitude=point.longitude,
        score=_time_score(point.delta_s) * _camera_factor(point),
        radius_m=_radius(point.delta_s),
        kind="before" if point.delta_s <= 0 else "after",
        evidence=_evidence(point),
    )


def _between(before: TrackPoint, after: TrackPoint) -> Candidate | None:
    gap = after.delta_s - before.delta_s
    distance = distance_m(before.latitude, before.longitude, after.latitude, after.longitude)
    if gap <= 0 or distance / gap > MAX_SPEED_M_S:
        return None
    share = -before.delta_s / gap
    nearest_gap = min(-before.delta_s, after.delta_s)
    return Candidate(
        latitude=before.latitude + (after.latitude - before.latitude) * share,
        longitude=before.longitude + (after.longitude - before.longitude) * share,
        # Bounded on both sides: as good as the closer neighbor, a bit better.
        score=min(1.0, _time_score(nearest_gap) * _camera_factor(before, after) * 1.1),
        radius_m=min(BASE_RADIUS_M + distance / 4 + SPEED_M_S * nearest_gap, MAX_RADIUS_M),
        kind="between",
        evidence=_evidence(before, after) | {"share": share},
    )


def _merge(candidates: list[Candidate]) -> list[Candidate]:
    """Best first; drops candidates within MERGE_DISTANCE_M of a better one."""
    kept: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda c: c.score, reverse=True):
        if all(
            distance_m(c.latitude, c.longitude, candidate.latitude, candidate.longitude)
            >= MERGE_DISTANCE_M
            for c in kept
        ):
            kept.append(candidate)
    return kept


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))
