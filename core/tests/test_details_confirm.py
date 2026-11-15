# SPDX-License-Identifier: AGPL-3.0-or-later
"""Suggestions of similar photos confirmed by matching details (D-225)."""

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_embeddings import encoded, run_module, start_worker
from test_similar_search import (
    BUDVA,
    KOTOR,
    KOTOR_NEAR,
    LEFT_HALF,
    PARIS,
    QUERY,
    evidence_files,
    library,  # noqa: F401
    similar,
)
from test_worker_api import db_call

from steward import details, worker_queue
from steward.models import Asset, DetailMatch, Job
from steward.modules.similar import CONFIRMED_SCORE

Library = dict[str, str]


def compared(client: TestClient, photo: str, other: str, inliers: int) -> None:
    """The answer of a worker: the two photos share this many points."""

    async def work(db: Any) -> None:
        db.add(
            DetailMatch(
                asset_id=UUID(photo),
                other_id=UUID(other),
                matches=inliers * 2,
                inliers=inliers,
                lines=[],
                module_version="1",
            )
        )
        await db.commit()

    db_call(client, work)


def places(module: dict[str, Any]) -> list[tuple[str, str, bool]]:
    return [
        (evidence_files(c)[0], c["tier"], c["evidence"]["confirmed"]) for c in module["candidates"]
    ]


def test_nothing_compared_changes_nothing(signed_in: TestClient, library: Library) -> None:  # noqa: F811
    module = similar(signed_in, library["query.jpg"])

    assert places(module) == [
        ("set-by-app.jpg", "confident", False),
        ("kotor.jpg", "confident", False),
        ("budva.jpg", "weak", False),
    ]
    assert all(
        n["details"] is None for c in module["candidates"] for n in c["evidence"]["neighbors"]
    )


def test_a_weak_suggestion_with_enough_shared_points_goes_first(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    compared(signed_in, library["query.jpg"], library["budva.jpg"], 150)

    module = similar(signed_in, library["query.jpg"])

    assert places(module) == [
        ("budva.jpg", "confident", True),
        ("set-by-app.jpg", "confident", False),
        ("kotor.jpg", "confident", False),
    ]
    budva = module["candidates"][0]
    assert (budva["rank"], budva["latitude"]) == (1, BUDVA["latitude"])
    assert budva["score"] == CONFIRMED_SCORE
    assert budva["evidence"]["neighbors"][0]["details"] == 150


def test_fewer_shared_points_are_shown_but_confirm_nothing(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    compared(signed_in, library["query.jpg"], library["budva.jpg"], 60)

    module = similar(signed_in, library["query.jpg"])

    assert places(module)[2] == ("budva.jpg", "weak", False)
    assert module["candidates"][2]["evidence"]["neighbors"][0]["details"] == 60


def test_the_threshold_is_a_setting(signed_in: TestClient, library: Library) -> None:  # noqa: F811
    compared(signed_in, library["query.jpg"], library["budva.jpg"], 60)
    assert signed_in.put("/api/settings", json={"details_confirmed_from": 50}).is_success

    assert places(similar(signed_in, library["query.jpg"]))[0] == ("budva.jpg", "confident", True)
    # Fewer than 8 points fit any geometry: not a threshold.
    assert signed_in.put("/api/settings", json={"details_confirmed_from": 7}).status_code == 422


def keys(client: TestClient, asset_id: str) -> list[str]:
    return [block["key"] for block in client.get(f"/api/assets/{asset_id}/suggestions").json()]


def test_similar_photos_with_a_confirmed_suggestion_go_before_every_module(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query = library["query.jpg"]
    assert keys(signed_in, query) == ["time_neighbors", "similar", "geoclip"]

    compared(signed_in, query, library["budva.jpg"], 150)

    assert keys(signed_in, query) == ["similar", "time_neighbors", "geoclip"]


def test_the_block_can_stay_where_the_account_put_it(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query = library["query.jpg"]
    compared(signed_in, query, library["budva.jpg"], 150)
    assert signed_in.put("/api/settings", json={"details_first": False}).is_success

    assert keys(signed_in, query) == ["time_neighbors", "similar", "geoclip"]
    # Within the block the confirmed suggestion is first all the same.
    module = similar(signed_in, query)
    assert places(module)[0] == ("budva.jpg", "confident", True)
    assert module["candidates"][0]["score"] == CONFIRMED_SCORE


def test_the_place_is_that_of_the_photo_sharing_the_points(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    # Two photos 300 m apart make one suggestion; the less similar one is the one confirmed.
    compared(signed_in, library["query.jpg"], library["kotor-near.jpg"], 130)
    compared(signed_in, library["query.jpg"], library["kotor.jpg"], 20)

    kotor = similar(signed_in, library["query.jpg"])["candidates"][0]

    assert evidence_files(kotor) == ["kotor-near.jpg", "kotor.jpg"]
    assert kotor["latitude"] == KOTOR_NEAR["latitude"] != KOTOR["latitude"]
    assert [n["details"] for n in kotor["evidence"]["neighbors"]] == [130, 20]
    assert kotor["evidence"]["confirmed"] is True


def test_a_suggestion_too_unlike_to_show_is_shown_when_confirmed(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    compared(signed_in, library["query.jpg"], library["paris.jpg"], 220)

    first = similar(signed_in, library["query.jpg"])["candidates"][0]

    assert (evidence_files(first), first["latitude"]) == (["paris.jpg"], PARIS["latitude"])


def test_the_answer_is_about_the_pair_whoever_was_asked(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    compared(signed_in, library["budva.jpg"], library["query.jpg"], 150)

    assert places(similar(signed_in, library["query.jpg"]))[0] == ("budva.jpg", "confident", True)


def test_a_part_of_the_photo_is_not_confirmed_by_the_whole(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    compared(signed_in, library["query.jpg"], library["budva.jpg"], 150)
    worker = start_worker(signed_in)
    run_module(
        signed_in, worker, library["query.jpg"], {"embedding": encoded(QUERY)}, region=LEFT_HALF
    )

    part = similar(signed_in, library["query.jpg"], key="similar:region")

    assert not any(c["evidence"]["confirmed"] for c in part["candidates"])
    assert places(part)[0][0] == "set-by-app.jpg"


# --- Which photos a photo is compared with ---


def queue_details(client: TestClient, asset_id: str, limit: int) -> list[str] | None:
    """Queues the comparison; the photos named in the job, by file name."""

    async def work(db: Any) -> list[str] | None:
        asset = await db.get(Asset, UUID(asset_id))
        run = await details.enqueue(db, asset, client.app.state.settings, limit)  # type: ignore[attr-defined]
        if run is None:
            return None
        job = await db.get(Job, run.job_id)
        names = dict((await db.execute(select(Asset.id, Asset.original_file_name))).all())
        return [names[other] for other in worker_queue.others_of(job)]

    result: list[str] | None = db_call(client, work)
    return result


def test_the_most_similar_photos_with_a_location_are_compared(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    assert queue_details(signed_in, library["query.jpg"], 3) == [
        "set-by-app.jpg",
        "kotor.jpg",
        "kotor-near.jpg",
    ]


def test_photos_compared_already_are_not_compared_again(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    compared(signed_in, library["query.jpg"], library["kotor.jpg"], 12)
    compared(signed_in, library["set-by-app.jpg"], library["query.jpg"], 30)

    assert queue_details(signed_in, library["query.jpg"], 3) == ["kotor-near.jpg"]
    # All of the nearest compared: nothing to queue.
    compared(signed_in, library["query.jpg"], library["kotor-near.jpg"], 9)
    assert queue_details(signed_in, library["query.jpg"], 3) is None


def test_a_photo_without_a_vector_has_nothing_to_compare_with(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    async def forget(db: Any) -> None:
        await worker_queue.forget_results(db, [UUID(library["query.jpg"])])
        await db.commit()

    db_call(signed_in, forget)

    assert queue_details(signed_in, library["query.jpg"], 3) is None


# --- The gallery ---


def gallery(client: TestClient, **params: Any) -> dict[str, bool]:
    """File name -> whether its tile is marked as confirmed by details."""
    items = client.get("/api/assets", params={"month": "2024-05", **params}).json()
    return {item["file_name"]: item["details_confirmed"] for item in items}


def test_the_gallery_marks_and_filters_the_photos_confirmed_by_details(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query = library["query.jpg"]
    assert not any(gallery(signed_in).values())
    assert gallery(signed_in, details_confirmed=True) == {}

    # Too few shared details confirm nothing.
    compared(signed_in, query, library["kotor.jpg"], 60)
    assert not any(gallery(signed_in).values())

    compared(signed_in, library["budva.jpg"], query, 150)
    assert [name for name, marked in gallery(signed_in).items() if marked] == ["query.jpg"]
    assert gallery(signed_in, details_confirmed=True) == {"query.jpg": True}

    # The threshold of the account applies to the gallery as to the card.
    signed_in.put("/api/settings", json={"details_confirmed_from": 200})
    assert gallery(signed_in, details_confirmed=True) == {}


def test_a_photo_with_a_location_is_not_marked(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    # Two photos with a location share details: neither needs a place.
    compared(signed_in, library["kotor.jpg"], library["kotor-near.jpg"], 300)

    assert not any(gallery(signed_in).values())
    assert gallery(signed_in, details_confirmed=True) == {}
