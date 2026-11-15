# SPDX-License-Identifier: AGPL-3.0-or-later
"""Location modules and their registry."""

from dataclasses import dataclass

from steward.models import EMBEDDING_DIM
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
    # Retrieval modules send the vector of the photo, of this length, instead of candidates.
    embedding_dim: int | None = None
    # False: the module suggests no places itself (`details` confirms those of another), so it
    # has no block in the card; it is still shown where the work of the workers is.
    suggests: bool = True


# Shown after the core modules, in this order.
REMOTE_MODULES: dict[str, RemoteModule] = {
    "geoclip": RemoteModule("geoclip", color="#bc4c00", shape="square"),
    "similar": RemoteModule(
        "similar", color="#1a7f37", shape="diamond", embedding_dim=EMBEDDING_DIM
    ),
    "details": RemoteModule("details", color="#bf8700", shape="triangle", suggests=False),
}
# Those with a block of suggestions in the card.
SUGGESTING_MODULES = {key: module for key, module in REMOTE_MODULES.items() if module.suggests}

__all__ = [
    "MODULES",
    "REMOTE_MODULES",
    "SUGGESTING_MODULES",
    "Candidate",
    "LocationModule",
    "ModuleContext",
    "ModuleResult",
    "RemoteModule",
    "TrackPoint",
]
