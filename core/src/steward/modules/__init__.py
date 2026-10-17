# SPDX-License-Identifier: AGPL-3.0-or-later
"""Location modules and their registry."""

from steward.modules.base import (
    Candidate,
    LocationModule,
    ModuleContext,
    ModuleResult,
    TrackPoint,
)
from steward.modules.time_neighbors import TimeNeighbors

# In display order. Third-party modules will be added through entry points (stage 6).
MODULES: list[LocationModule] = [TimeNeighbors()]

__all__ = [
    "MODULES",
    "Candidate",
    "LocationModule",
    "ModuleContext",
    "ModuleResult",
    "TrackPoint",
]
