# SPDX-License-Identifier: AGPL-3.0-or-later
"""Modules this worker can run, by id."""

from collections.abc import Callable

from steward_worker.modules.base import Candidate, Embedding, PermanentError, WorkerModule
from steward_worker.modules.geoclip import GeoClipModule, ModuleOptions
from steward_worker.modules.similar import SimilarModule

# A factory per module: models are heavy, so only the modules a worker is asked to run are
# created, and they load their models (and import PyTorch) only on their first job. The order is
# the default priority of their background jobs: the index of similar photos first, without it
# they have nothing to suggest.
AVAILABLE: dict[str, Callable[[ModuleOptions], WorkerModule]] = {
    SimilarModule.id: SimilarModule,
    GeoClipModule.id: GeoClipModule,
}

__all__ = [
    "AVAILABLE",
    "Candidate",
    "Embedding",
    "ModuleOptions",
    "PermanentError",
    "WorkerModule",
]
