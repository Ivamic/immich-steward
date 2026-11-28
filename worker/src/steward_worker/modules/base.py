# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract of the modules a worker runs."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

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
    # Points on people, animals or vehicles (the groups the core asked for) were left out of
    # either photo before the matching (D-248); None: no masks were asked for.
    masked: bool | None = None


@dataclass(frozen=True)
class StreetMatch(PairMatch):
    """How a street-level image matches the photo (the `street` module): how alike they look
    and, for the most alike ones, point by point; with the way the photo looks from it."""

    # Cosine of the MegaLoc vectors of the photo and the image (its best view, for a panorama).
    similarity: float = 0.0
    # Compared point by point: `matches`, `inliers` and `lines` are known.
    checked: bool = False
    # A 360-degree panorama: which of its views around the horizon looks most like the photo
    # (0: its middle, then every 360/views degrees to the right).
    view: int | None = None
    # Degrees the photo looks to the right of the way the image looks (its middle), and how far
    # the points spread around that; None when too few points fit.
    offset: float | None = None
    spread: float | None = None
    # The width of view of the photo the offset was worked out with (found from the points).
    fov: float | None = None


@dataclass(frozen=True)
class Orientation:
    """How the photo is turned (the `orientation` module): the chance of each turn it has now,
    0, 90 degrees counter-clockwise, 180, 90 degrees clockwise."""

    probs: tuple[float, float, float, float]
    # How many turns of the photo were looked at: 1, or 4 when the first look said "turned".
    looks: int = 1


@dataclass(frozen=True)
class Objects:
    """What is in the photo (the `objects` module, D-248): people, animals and vehicles as
    groups, every object found, and where they are."""

    # By group ("person", "animal", "vehicle"), the ones found only: how many and the share of
    # the photo they cover (0..1).
    groups: dict[str, dict[str, float]]
    # Every object of the 80 classes of COCO: class, confidence, box (x1, y1, x2, y2, 0..1).
    found: list[dict[str, Any]]
    # The label map, its long side `objects.KEEP_SIDE`, as a PNG: 0 nothing, then the groups
    # (`objects.LABEL`); for showing the masks.
    labels: bytes


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

    def run(self, image: bytes) -> list[Candidate] | Embedding | Orientation | Objects:
        """Candidate locations for one image (JPEG or WebP), its vector, or how it is turned.
        Runs in a thread."""
        ...


@runtime_checkable
class PairModule(Protocol):
    """A module that compares the photo of a job with other photos the core names, instead of
    suggesting places for it (`details`). Loaded and unloaded like a `WorkerModule`."""

    id: str
    version: str

    def load(self) -> None: ...

    def unload(self) -> None: ...

    def compare(self, image: bytes, others: Sequence[bytes]) -> Sequence[PairMatch | None]:
        """The photo against each of the others, in their order; None where the other photo
        cannot be read. Runs in a thread. A module may take `masks` too (`details`, D-248): the
        groups the core asks to leave out, given when the job names them."""
        ...
