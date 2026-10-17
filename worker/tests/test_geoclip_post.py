# SPDX-License-Identifier: AGPL-3.0-or-later
"""Post-processing of GeoCLIP predictions (no model needed)."""

import pytest

from steward_worker.modules import AVAILABLE, ModuleOptions
from steward_worker.modules.clustering import cluster_points, distance_m
from steward_worker.modules.geoclip import MAX_RADIUS_M, MIN_RADIUS_M, to_candidates

ROME = (41.9, 12.5)
NEAR_ROME = (41.95, 12.45)  # ~7 km away
MILAN = (45.46, 9.19)
PARIS = (48.86, 2.35)


def test_distance() -> None:
    assert distance_m(*ROME, *MILAN) == pytest.approx(477_000, rel=0.01)


def test_close_points_form_one_area_weighted_to_the_heavier() -> None:
    [area, other] = cluster_points([ROME, NEAR_ROME, MILAN], [0.5, 0.2, 0.1], 25_000, 5)
    assert area.members == 2
    assert area.weight == pytest.approx(0.7)
    assert distance_m(area.latitude, area.longitude, *ROME) < distance_m(
        area.latitude, area.longitude, *NEAR_ROME
    )
    assert (other.latitude, other.longitude) == MILAN


def test_heaviest_areas_first_and_limited() -> None:
    clusters = cluster_points([PARIS, MILAN, ROME], [0.1, 0.3, 0.2], 25_000, 2)
    assert [(c.latitude, c.longitude) for c in clusters] == [MILAN, ROME]


def test_candidates_drop_noise_and_bound_the_radius() -> None:
    candidates = to_candidates([ROME, NEAR_ROME, PARIS], [0.6, 0.3, 0.01])
    assert len(candidates) == 1  # Paris is below the noise level
    [rome] = candidates
    assert rome.kind == "area"
    assert rome.score == pytest.approx(0.9)
    assert rome.evidence == {"points": 2}
    assert MIN_RADIUS_M <= (rome.radius_m or 0) <= MAX_RADIUS_M


def test_module_is_registered_without_importing_torch() -> None:
    module = AVAILABLE["geoclip"](ModuleOptions(threads=1, device="cpu"))
    assert (module.id, module.version) == ("geoclip", "1")
