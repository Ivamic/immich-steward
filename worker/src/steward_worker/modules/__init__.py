# SPDX-License-Identifier: AGPL-3.0-or-later
"""Modules this worker can run, by id."""

from collections.abc import Callable

from steward_worker.modules.base import (
    Candidate,
    Embedding,
    Orientation,
    PairMatch,
    PairModule,
    PermanentError,
    WorkerModule,
)
from steward_worker.modules.details import DetailsModule
from steward_worker.modules.geoclip import GeoClipModule, ModuleOptions
from steward_worker.modules.orientation import OrientationModule
from steward_worker.modules.similar import SimilarModule

# A factory per module: models are heavy, so only the modules a worker is asked to run are
# created, and they load their models (and import PyTorch) only on their first job. The order is
# the default priority of their background jobs: the index of similar photos first, without it
# they have nothing to suggest; the details only confirm what the others found; the turned
# photos are no location at all, so they come last.
AVAILABLE: dict[str, Callable[[ModuleOptions], WorkerModule | PairModule]] = {
    SimilarModule.id: SimilarModule,
    GeoClipModule.id: GeoClipModule,
    DetailsModule.id: DetailsModule,
    OrientationModule.id: OrientationModule,
}

__all__ = [
    "AVAILABLE",
    "Candidate",
    "Embedding",
    "ModuleOptions",
    "Orientation",
    "PairMatch",
    "PairModule",
    "PermanentError",
    "WorkerModule",
]
