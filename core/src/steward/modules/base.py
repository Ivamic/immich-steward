# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract of location modules.

A module looks at one asset and returns candidate locations. It never writes to Immich: writing
happens only when the user accepts a location (FR-53).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from steward.config import Settings
from steward.models import Account, Asset

MarkerShape = Literal["circle", "square", "diamond", "star", "triangle", "pentagon"]


@dataclass(frozen=True)
class Candidate:
    latitude: float
    longitude: float
    # 0..1; comparable only within one module.
    score: float
    # Estimated error, drawn as a circle on the map.
    radius_m: float | None
    # Module-specific kind of the candidate; the UI turns it (with `evidence`) into a label.
    kind: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrackPoint:
    """A located photo near the asset in time, for drawing the route on the map."""

    asset_id: UUID
    latitude: float
    longitude: float
    local_taken_at: datetime
    # Seconds from the asset; negative means before it.
    delta_s: float
    file_name: str
    # Camera as shown to the user ("" when unknown).
    camera: str
    same_camera: bool
    # The location was written by this app, not recorded by the camera.
    estimated: bool
    role: Literal["before", "after"] | None = None
    # Changes with the thumbnails (`AssetItem.version`).
    version: str | None = None


@dataclass(frozen=True)
class CameraCount:
    """A camera whose photos the module looked at; the user may exclude it."""

    # make + CAMERA_SEPARATOR + model, as in the gallery camera filter.
    value: str
    label: str
    count: int
    same_camera: bool
    excluded: bool


@dataclass
class ModuleResult:
    candidates: list[Candidate] = field(default_factory=list)
    track: list[TrackPoint] = field(default_factory=list)
    cameras: list[CameraCount] = field(default_factory=list)
    # Why there are no candidates, e.g. "scanner"; translated by the UI.
    note: str | None = None


@dataclass(frozen=True)
class ModuleContext:
    db: AsyncSession
    account: Account
    asset: Asset
    settings: Settings
    # Cameras the user excluded for this photo (camera filter values).
    exclude_cameras: frozenset[str] = frozenset()
    # Only photos of the photo's own camera count (when the camera is known).
    same_camera_only: bool = False
    # Locations saved in the browser a moment ago and not sent yet: asset id -> (lat, lon).
    pending: Mapping[UUID, tuple[float, float]] = field(default_factory=dict)


class LocationModule(Protocol):
    id: str
    # Changes when the algorithm or model changes (reason to run the module again).
    version: str
    color: str
    shape: MarkerShape
    # external modules send photos to third parties and never run automatically (FR-70…73).
    privacy: Literal["local", "external"]

    async def run(self, ctx: ModuleContext) -> ModuleResult: ...
