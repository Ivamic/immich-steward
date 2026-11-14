# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which matched points of two photos agree with one geometry.

Two photos of the same rigid scene taken from two places are tied by a fundamental matrix F:
for a point x in the first photo and its match x' in the second, x'ᵀ F x = 0. Matches of things
that only look alike (windows of two different houses) do not share one F. RANSAC finds the F
most matches agree with; the matches within a few pixels of it are the "inliers".

Plain NumPy, so that the worker needs no OpenCV.
"""

from typing import Any

import numpy as np

# Fewer matches always fit some F: the answer would say nothing.
MIN_MATCHES = 8
SAMPLE = 8
# Samples checked at once: bounds the memory when there are thousands of matches.
CHUNK = 250


def _normalize(points: Any) -> tuple[Any, Any]:
    """Hartley normalization: centroid at zero, mean distance √2. Returns the points and the map."""
    center = points.mean(axis=0)
    spread = np.sqrt(((points - center) ** 2).sum(axis=1)).mean()
    scale = np.sqrt(2.0) / max(spread, 1e-9)
    transform = np.array(
        [[scale, 0.0, -scale * center[0]], [0.0, scale, -scale * center[1]], [0.0, 0.0, 1.0]]
    )
    return (points - center) * scale, transform


def _eight_point(a: Any, b: Any) -> Any:
    """F of every sample: a and b are (samples, n, 2) normalized points, n ≥ 8."""
    ax, ay, bx, by = a[..., 0], a[..., 1], b[..., 0], b[..., 1]
    ones = np.ones_like(ax)
    design = np.stack([bx * ax, bx * ay, bx, by * ax, by * ay, by, ax, ay, ones], axis=-1)
    _, _, vt = np.linalg.svd(design, full_matrices=True)
    f = vt[:, -1, :].reshape(-1, 3, 3)
    # A fundamental matrix has rank 2.
    u, s, vt = np.linalg.svd(f)
    s[:, 2] = 0.0
    return (u * s[:, None, :]) @ vt


def _sampson(f: Any, a: Any, b: Any) -> Any:
    """Squared Sampson distance of every match to every F: (samples, matches).

    `a` and `b` are (matches, 3) homogeneous pixel coordinates.
    """
    fa = a @ f.transpose(0, 2, 1)  # F x, one row per match
    ftb = b @ f  # Fᵀ x'
    error = (b * fa).sum(axis=-1)
    denominator = fa[..., 0] ** 2 + fa[..., 1] ** 2 + ftb[..., 0] ** 2 + ftb[..., 1] ** 2
    return error**2 / np.maximum(denominator, 1e-12)


def geometry_inliers(
    first: Any,
    second: Any,
    *,
    threshold_px: float = 3.0,
    iterations: int = 2000,
    seed: int = 0,
) -> Any:
    """A boolean mask of the matches that agree with the best fundamental matrix.

    `first` and `second` are (n, 2) pixel coordinates of the matched points, row by row.
    The same input gives the same answer (fixed seed).
    """
    first = np.asarray(first, dtype=np.float64).reshape(-1, 2)
    second = np.asarray(second, dtype=np.float64).reshape(-1, 2)
    count = len(first)
    if count < MIN_MATCHES:
        return np.zeros(count, dtype=bool)
    a, ta = _normalize(first)
    b, tb = _normalize(second)
    rng = np.random.default_rng(seed)
    # A repeated point in a sample only wastes that sample.
    picks = rng.integers(0, count, size=(iterations, SAMPLE))
    # Back to pixels: the threshold is in pixels.
    f = tb.T @ _eight_point(a[picks], b[picks]) @ ta
    ones = np.ones((count, 1))
    ha, hb = np.hstack([first, ones]), np.hstack([second, ones])
    limit = threshold_px**2
    best_f, best_count = f[:1], -1
    for start in range(0, iterations, CHUNK):
        part = f[start : start + CHUNK]
        counts = (_sampson(part, ha, hb) <= limit).sum(axis=1)
        top = int(np.argmax(counts))
        if counts[top] > best_count:
            best_f, best_count = part[top : top + 1], int(counts[top])
    best = _sampson(best_f, ha, hb)[0] <= limit
    # One more fit on everything the best sample agrees with, kept if it agrees with more.
    if best.sum() >= MIN_MATCHES:
        refit = tb.T @ _eight_point(a[best][None], b[best][None]) @ ta
        again = _sampson(refit, ha, hb)[0] <= limit
        if again.sum() > best.sum():
            best = again
    return best
