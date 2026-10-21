# SPDX-License-Identifier: AGPL-3.0-or-later
"""Modules this worker can run, by id."""

from collections.abc import Callable

from steward_worker.modules.base import Candidate, Embedding, PermanentError, WorkerModule
from steward_worker.modules.geoclip import GeoClipModule, ModuleOptions
from steward_worker.modules.similar import SimilarModule

# A factory per module: models are heavy, so only the modules a worker is asked to run are
# created, and they load their models (and import PyTorch) only on their first job.
AVAILABLE: dict[str, Callable[[ModuleOptions], WorkerModule]] = {
    GeoClipModule.id: GeoClipModule,
    SimilarModule.id: SimilarModule,
}

__all__ = [
    "AVAILABLE",
    "Candidate",
    "Embedding",
    "ModuleOptions",
    "PermanentError",
    "WorkerModule",
]
