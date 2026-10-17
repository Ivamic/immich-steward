# SPDX-License-Identifier: AGPL-3.0-or-later
"""Location modules and their registry."""

from dataclasses import dataclass

from steward.modules.base import (
    Candidate,
    LocationModule,
    MarkerShape,
    ModuleContext,
    ModuleResult,
    TrackPoint,
)
from steward.modules.time_neighbors import TimeNeighbors

# In display order. Third-party modules will be added through entry points (stage 6).
MODULES: list[LocationModule] = [TimeNeighbors()]


@dataclass(frozen=True)
class RemoteModule:
    """A module run by workers; the core only knows how to show its results."""

    id: str
    color: str
    shape: MarkerShape


# Shown after the core modules, in this order.
REMOTE_MODULES: dict[str, RemoteModule] = {
    "geoclip": RemoteModule("geoclip", color="#bc4c00", shape="square"),
}

__all__ = [
    "MODULES",
    "REMOTE_MODULES",
    "Candidate",
    "LocationModule",
    "ModuleContext",
    "ModuleResult",
    "RemoteModule",
    "TrackPoint",
]
