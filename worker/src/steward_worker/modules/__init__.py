# SPDX-License-Identifier: AGPL-3.0-or-later
"""Modules this worker can run, by id."""

from collections.abc import Callable

from steward_worker.modules.base import Candidate, PermanentError, WorkerModule
from steward_worker.modules.geoclip import GeoClipModule, ModuleOptions

# A factory per module: models are heavy, so only the modules a worker is asked to run are
# created, and they load their models (and import PyTorch) only on their first job.
AVAILABLE: dict[str, Callable[[ModuleOptions], WorkerModule]] = {
    GeoClipModule.id: GeoClipModule,
}

__all__ = ["AVAILABLE", "Candidate", "ModuleOptions", "PermanentError", "WorkerModule"]
