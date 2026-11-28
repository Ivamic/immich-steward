# SPDX-License-Identifier: AGPL-3.0-or-later
"""Masks of people and animals before matching details (D-248, D-256)."""

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_details_confirm import places
from test_details_runs import worker_on
from test_similar_search import library, similar  # noqa: F401
from test_worker_api import db_call

from steward import masks, worker_queue
from steward.models import Asset, AssetObjects, DetailMatch, Job, ModuleRun

Library = dict[str, str]
PERSON_KEY = "person+animal:6"


def compared(
    client: TestClient,
    photo: str,
    other: str,
    inliers: int,
    masked: bool | None = None,
    key: str | None = None,
) -> None:
    async def work(db: Any) -> None:
        db.add(
            DetailMatch(
                asset_id=UUID(photo),
                other_id=UUID(other),
                matches=inliers * 2,
                inliers=inliers,
                lines=[],
                module_version="1",
                masked=masked,
                mask_key=key,
            )
        )
        await db.commit()

    db_call(client, work)


def found(client: TestClient, photo: str, groups: dict[str, Any]) -> None:
    """The answer of the module `objects` for the photo."""

    async def work(db: Any) -> None:
        run = ModuleRun(asset_id=UUID(photo), module_id="objects", status="done")
        db.add(run)
        await db.flush()
        db.add(
            AssetObjects(
                asset_id=UUID(photo),
                run_id=run.id,
                groups=groups,
                found=[],
                labels=b"png",
                module_version="1",
            )
        )
        await db.commit()

    db_call(client, work)


def pair(client: TestClient, photo: str, other: str) -> DetailMatch:
    async def work(db: Any) -> DetailMatch:
        row = await db.get(DetailMatch, (UUID(photo), UUID(other)))
        assert row is not None
        return row  # type: ignore[no-any-return]

    result: DetailMatch = db_call(client, work)
    return result


def alpha(image: Any, at: tuple[int, int]) -> int:
    value = image.getpixel(at)
    assert isinstance(value, tuple)
    return int(value[3])


def requeue(client: TestClient) -> int:
    async def work(db: Any) -> int:
        return await masks.requeue(db)

    result: int = db_call(client, work)
    return result


def queued_others(client: TestClient, photo: str) -> list[str]:
    async def work(db: Any) -> list[str]:
        job = await db.scalar(
            select(Job)
            .join(ModuleRun, ModuleRun.job_id == Job.id)
            .where(ModuleRun.asset_id == UUID(photo), ModuleRun.module_id == "details")
        )
        return worker_queue.others_of(job) if job else []

    result: list[str] = db_call(client, work)
    return result


def lease(client: TestClient, worker: dict[str, str]) -> Any:
    return client.post("/api/worker/lease", json={"modules": ["details"]}, headers=worker)


def ask(client: TestClient, library: Library, others: list[str]) -> None:  # noqa: F811
    """A comparison of the query photo started by hand."""

    async def work(db: Any) -> None:
        asset = await db.get(Asset, UUID(library["query.jpg"]))
        await worker_queue.enqueue_pairs(
            db, asset, "details", [UUID(library[o]) for o in others], worker_queue.PRIORITY_USER
        )

    db_call(client, work)


def test_a_worker_before_0_15_compares_nothing_while_masks_are_on(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    ask(signed_in, library, ["kotor.jpg"])
    old = worker_on(signed_in, "cuda", name="old")
    signed_in.post(
        "/api/worker/register",
        json={
            "name": "old",
            "modules": ["details"],
            "device": "cuda",
            "version": "0.14.0",
            "protocol_version": 1,
        },
        headers={"Authorization": old["Authorization"]},
    )
    assert lease(signed_in, old).status_code == 204
    # With the masks off, it does.
    assert signed_in.put("/api/settings", json={"masks_enabled": False}).is_success
    job = lease(signed_in, old)
    assert job.status_code == 200
    assert job.json()["masks"] is None


def test_the_job_names_the_masks_and_the_answer_keeps_them(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    ask(signed_in, library, ["kotor.jpg", "budva.jpg"])
    worker = worker_on(signed_in, "cuda")
    job = lease(signed_in, worker).json()
    assert job["masks"] == {"groups": ["person", "animal"], "grow": 6}
    body = {
        "module_version": "1",
        "candidates": [],
        "pairs": [
            {"other": library["kotor.jpg"], "matches": 100, "inliers": 85, "masked": True},
            {"other": library["budva.jpg"], "matches": 50, "inliers": 20, "masked": False},
        ],
    }
    done = signed_in.post(f"/api/worker/jobs/{job['job_id']}/result", json=body, headers=worker)
    assert done.status_code == 204
    kotor = pair(signed_in, library["query.jpg"], library["kotor.jpg"])
    assert (kotor.masked, kotor.mask_key) == (True, PERSON_KEY)
    budva = pair(signed_in, library["query.jpg"], library["budva.jpg"])
    assert (budva.masked, budva.mask_key) == (False, PERSON_KEY)


def test_a_masked_pair_confirms_from_80_points(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    # 85 points: not enough without masks (100), enough with them (80).
    compared(signed_in, library["query.jpg"], library["budva.jpg"], 85, masked=False)
    assert ("budva.jpg", "confident", True) not in places(similar(signed_in, library["query.jpg"]))

    async def mask(db: Any) -> None:
        row = await db.get(DetailMatch, (UUID(library["query.jpg"]), UUID(library["budva.jpg"])))
        row.masked = True
        await db.commit()

    db_call(signed_in, mask)
    assert places(similar(signed_in, library["query.jpg"]))[0] == ("budva.jpg", "confident", True)
    items = signed_in.get(
        "/api/assets", params={"month": "2024-05", "details_confirmed": True}
    ).json()
    assert [item["file_name"] for item in items] == ["query.jpg"]
    # The threshold is a personal setting.
    assert signed_in.put("/api/settings", json={"details_masked_from": 90}).is_success
    assert places(similar(signed_in, library["query.jpg"]))[0][2] is False


def test_pairs_compared_before_masks_are_brought_to_them(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query, kotor, budva = library["query.jpg"], library["kotor.jpg"], library["budva.jpg"]
    near = library["kotor-near.jpg"]
    compared(signed_in, query, kotor, 150)  # before 0.15: no key
    compared(signed_in, query, budva, 30)
    compared(signed_in, query, near, 40)
    # Kotor shows a person; Budva nothing; the other photo of Kotor is not looked at yet.
    found(signed_in, query, {})
    found(signed_in, kotor, {"person": {"count": 1, "cover": 0.2}})
    found(signed_in, budva, {"vehicle": {"count": 2, "cover": 0.1}})

    assert requeue(signed_in) == 1
    # Nothing of the groups in either photo: the same answer, only the key.
    assert pair(signed_in, query, budva).mask_key == PERSON_KEY
    # A person in one of them: compared again; waiting for `objects`: left as it is.
    assert queued_others(signed_in, query) == [kotor]
    assert pair(signed_in, query, kotor).mask_key is None
    assert pair(signed_in, query, near).mask_key is None
    # Queued once.
    assert requeue(signed_in) == 0


def test_masks_turned_off_compare_again_only_the_masked_pairs(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query, kotor, budva = library["query.jpg"], library["kotor.jpg"], library["budva.jpg"]
    compared(signed_in, query, kotor, 90, masked=True, key=PERSON_KEY)
    compared(signed_in, query, budva, 30, masked=False, key=PERSON_KEY)
    assert signed_in.put("/api/settings", json={"masks_enabled": False}).is_success

    assert requeue(signed_in) == 1
    assert queued_others(signed_in, query) == [kotor]
    budva_pair = pair(signed_in, query, budva)
    assert (budva_pair.mask_key, budva_pair.masked) == ("off", None)


def test_a_photo_compared_again_forgets_its_comparisons(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    query = library["query.jpg"]
    compared(signed_in, query, library["kotor.jpg"], 150)
    compared(signed_in, library["budva.jpg"], query, 120)
    response = signed_in.post(f"/api/assets/{query}/details/again")
    assert response.status_code == 200

    async def left(db: Any) -> int:
        return len((await db.scalars(select(DetailMatch))).all())

    assert db_call(signed_in, left) == 0
    # Queued ahead of the background, with its most similar photos (5 by default).
    assert len(queued_others(signed_in, query)) == 5


def test_every_comparison_can_be_forgotten(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    compared(signed_in, library["query.jpg"], library["kotor.jpg"], 150)

    async def ran(db: Any) -> None:
        db.add(ModuleRun(asset_id=UUID(library["query.jpg"]), module_id="details", status="done"))
        await db.commit()

    db_call(signed_in, ran)
    assert signed_in.get("/api/library/details/reset").json() == {"photos": 1}
    assert signed_in.post("/api/library/details/reset").json() == {"photos": 1}
    assert signed_in.get("/api/library/details/reset").json() == {"photos": 0}
    assert signed_in.get("/api/settings/masks").json() == {"pending": 0}


def test_little_background_and_the_mask_picture(
    signed_in: TestClient,
    library: Library,  # noqa: F811
) -> None:
    import io

    from PIL import Image

    labels = io.BytesIO()
    Image.fromarray(__import__("numpy").array([[1, 2], [0, 3]], dtype="uint8")).save(
        labels, format="PNG"
    )

    async def store(db: Any, photo: str, groups: dict[str, Any]) -> None:
        run = ModuleRun(asset_id=UUID(photo), module_id="objects", status="done")
        db.add(run)
        await db.flush()
        db.add(
            AssetObjects(
                asset_id=UUID(photo),
                run_id=run.id,
                groups=groups,
                found=[],
                labels=labels.getvalue(),
                module_version="1",
            )
        )
        await db.commit()

    close_up = {"person": {"count": 1, "cover": 0.6}, "animal": {"count": 1, "cover": 0.2}}
    db_call(signed_in, lambda db: store(db, library["query.jpg"], close_up))
    db_call(
        signed_in,
        lambda db: store(db, library["kotor.jpg"], {"person": {"count": 1, "cover": 0.3}}),
    )

    detail = signed_in.get(f"/api/assets/{library['query.jpg']}").json()
    assert detail["little_background"] is True
    assert detail["objects"] == close_up
    assert signed_in.get(f"/api/assets/{library['kotor.jpg']}").json()["little_background"] is False
    items = signed_in.get(
        "/api/assets",
        params={"month": "2024-05", "show": ["todo", "with"], "little_background": True},
    ).json()
    assert [item["file_name"] for item in items] == ["query.jpg"]
    # Without the animals 0.6 is not enough.
    assert signed_in.put("/api/settings", json={"masks_groups": ["person"]}).is_success
    assert signed_in.get(f"/api/assets/{library['query.jpg']}").json()["little_background"] is False

    picture = signed_in.get(f"/api/assets/{library['query.jpg']}/mask.png")
    assert picture.headers["content-type"] == "image/png"
    pixels = Image.open(io.BytesIO(picture.content))
    assert pixels.mode == "RGBA"
    assert alpha(pixels, (0, 0)) > 0  # the person
    assert alpha(pixels, (1, 0)) == 0  # the animal: not chosen now
    both = signed_in.get(
        f"/api/assets/{library['query.jpg']}/mask.png", params={"groups": ["person", "animal"]}
    )
    assert alpha(Image.open(io.BytesIO(both.content)), (1, 0)) > 0
    assert signed_in.get(f"/api/assets/{library['budva.jpg']}/mask.png").status_code == 404
