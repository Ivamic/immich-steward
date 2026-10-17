# SPDX-License-Identifier: AGPL-3.0-or-later
"""Modules this worker can run, by id."""

from collections.abc import Callable

from steward_worker.modules.base import Candidate, PermanentError, WorkerModule

# Filled in as modules are added (GeoCLIP next). A factory per module: models are heavy, so only
# the modules a worker is asked to run are created.
AVAILABLE: dict[str, Callable[[], WorkerModule]] = {}

__all__ = ["AVAILABLE", "Candidate", "PermanentError", "WorkerModule"]
