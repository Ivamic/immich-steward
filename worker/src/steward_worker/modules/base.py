# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract of the modules a worker runs."""

from dataclasses import dataclass, field
from typing import Any, Protocol

# What the core sends: the previews of Immich (JPEG or WebP) or parts it cut (JPEG). Pillow would
# try every format it knows otherwise, and the rare ones have had most of the decoder bugs.
IMAGE_FORMATS = ("JPEG", "WEBP", "PNG")


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


@dataclass(frozen=True)
class Embedding:
    """What a retrieval module returns instead of candidates: a vector of the photo, with which
    the core searches the user's own library (M3)."""

    # Little-endian float16, `dim` numbers.
    data: bytes
    dim: int


@dataclass(frozen=True)
class PairMatch:
    """How well two photos match point by point (the `details` module)."""

    # Points paired up between the two photos.
    matches: int
    # Of them, the pairs that fit one geometry: the same scene seen from two places.
    inliers: int
    # Some of those pairs for drawing: x, y in the first photo and x, y in the second, 0..1 of
    # the width and the height.
    lines: list[tuple[float, float, float, float]] = field(default_factory=list)


class PermanentError(Exception):
    """Running the job again cannot help (e.g. the image cannot be decoded)."""


class WorkerModule(Protocol):
    id: str
    # Changes when the model or the algorithm changes; stored with the result.
    version: str

    def load(self) -> None:
        """Loads the model; called before the first job and again after `unload`.

        A module may also have `weights_cached() -> bool`: False when `load` has to download the
        weights first, so that the worker can say it is downloading, not just loading.
        """

    def unload(self) -> None:
        """Frees the memory of the model when the worker has been idle for a while."""

    def run(self, image: bytes) -> list[Candidate] | Embedding:
        """Candidate locations for one image (JPEG or WebP), or its vector. Runs in a thread."""
        ...
