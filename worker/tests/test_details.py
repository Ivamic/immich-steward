# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

np = pytest.importorskip("numpy")

from steward_worker.modules.geometry import MIN_MATCHES, geometry_inliers  # noqa: E402


def two_views(points: int, seed: int = 1) -> tuple["np.ndarray", "np.ndarray"]:
    """The same 3D points seen by two cameras a step apart, in pixels of 1024 x 768 photos."""
    rng = np.random.default_rng(seed)
    world = np.column_stack(
        [rng.uniform(-4, 4, points), rng.uniform(-3, 3, points), rng.uniform(6, 20, points)]
    )
    focal, center = 800.0, np.array([512.0, 384.0])
    angle = np.radians(12)
    turn = np.array(
        [[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]]
    )
    moved = world @ turn.T + np.array([1.5, 0.1, 0.3])

    def project(xyz: "np.ndarray") -> "np.ndarray":
        return focal * xyz[:, :2] / xyz[:, 2:3] + center

    return project(world), project(moved)


def test_points_of_one_scene_agree() -> None:
    first, second = two_views(200)
    rng = np.random.default_rng(2)
    second = second + rng.normal(0, 0.5, second.shape)

    assert geometry_inliers(first, second).sum() >= 190


def test_wrong_pairs_are_left_out() -> None:
    first, second = two_views(150)
    rng = np.random.default_rng(3)
    wrong = rng.uniform(0, 1, (100, 2)) * [1024, 768]
    first = np.vstack([first, rng.uniform(0, 1, (100, 2)) * [1024, 768]])
    second = np.vstack([second, wrong])

    mask = geometry_inliers(first, second)

    assert mask[:150].sum() >= 140
    assert mask[150:].sum() <= 15


def test_random_pairs_have_few_in_agreement() -> None:
    rng = np.random.default_rng(4)
    first = rng.uniform(0, 1, (300, 2)) * [1024, 768]
    second = rng.uniform(0, 1, (300, 2)) * [1024, 768]

    assert geometry_inliers(first, second).sum() < 40


def test_too_few_pairs_say_nothing() -> None:
    first, second = two_views(MIN_MATCHES - 1)

    assert geometry_inliers(first, second).sum() == 0
    assert geometry_inliers(np.empty((0, 2)), np.empty((0, 2))).shape == (0,)


def test_same_input_same_answer() -> None:
    first, second = two_views(120)

    assert (geometry_inliers(first, second) == geometry_inliers(first, second)).all()
