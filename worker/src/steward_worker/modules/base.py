# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract of the modules a worker runs."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Candidate:
    latitude: float
    longitude: float
    # 0..1; comparable only within one module.
    score: float
    # Estimated error in meters, drawn as a circle on the map.
    radius_m: float | None = None
    # Module-specific kind; the web UI turns it into a label.
    kind: str = "point"
    evidence: dict[str, Any] = field(default_factory=dict)


class PermanentError(Exception):
    """Running the job again cannot help (e.g. the image cannot be decoded)."""


class WorkerModule(Protocol):
    id: str
    # Changes when the model or the algorithm changes; stored with the result.
    version: str

    def load(self) -> None:
        """Loads the model; called before the first job and again after `unload`."""

    def unload(self) -> None:
        """Frees the memory of the model when the worker has been idle for a while."""

    def run(self, image: bytes) -> list[Candidate]:
        """Candidate locations for one image (JPEG or WebP). Runs in a thread."""
        ...
