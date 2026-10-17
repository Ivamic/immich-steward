# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turning many weighted point predictions into a few candidate areas."""

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000.0


@dataclass
class Cluster:
    latitude: float
    longitude: float
    # Sum of the probabilities of the member points.
    weight: float
    members: int
    # Probability-weighted mean distance of the members from the center.
    spread_m: float


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


def cluster_points(
    points: list[tuple[float, float]],
    weights: list[float],
    join_m: float,
    limit: int,
) -> list[Cluster]:
    """Greedy clustering, heaviest point first.

    A point joins the first cluster whose seed (its heaviest point) is within `join_m`; otherwise
    it starts a new cluster. The center is the weighted mean of the members (fine at the scale of
    `join_m`, far from the antimeridian). Returns the `limit` heaviest clusters.
    """
    order = sorted(range(len(points)), key=lambda i: weights[i], reverse=True)
    seeds: list[tuple[float, float]] = []
    groups: list[list[int]] = []
    for i in order:
        lat, lon = points[i]
        for seed, group in zip(seeds, groups, strict=True):
            if distance_m(seed[0], seed[1], lat, lon) <= join_m:
                group.append(i)
                break
        else:
            seeds.append((lat, lon))
            groups.append([i])

    clusters = []
    for group in groups:
        total = sum(weights[i] for i in group) or 1e-12
        lat = sum(points[i][0] * weights[i] for i in group) / total
        lon = sum(points[i][1] * weights[i] for i in group) / total
        spread = sum(distance_m(lat, lon, *points[i]) * weights[i] for i in group) / total
        clusters.append(Cluster(lat, lon, sum(weights[i] for i in group), len(group), spread))
    clusters.sort(key=lambda c: c.weight, reverse=True)
    return clusters[:limit]
