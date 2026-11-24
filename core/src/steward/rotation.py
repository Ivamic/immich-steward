# SPDX-License-Identifier: AGPL-3.0-or-later
"""Saving the turn the user gave a photo in the app to Immich, as an edit (Immich 2.5+).

Immich keeps edits apart from the original file, which stays as it is, and makes new thumbnails
from them. Only called when the user asks for it.
"""

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from steward import worker_queue
from steward.errors import ApiError
from steward.immich import ImmichClient
from steward.models import Asset, AssetOrientation, Job

JOB_KIND = "rotate"
# The jobs that no longer turn their photos.
FINISHED = ("done", "failed")

# Waiting for Immich to make the new thumbnails: up to 10 s.
THUMBNAIL_POLL_S = 0.5
THUMBNAIL_ATTEMPTS = 20


def turning() -> ColumnElement[bool]:
    """The photo waits for a rotate job, or is being turned by one: a turn on top of it would
    add up with the first (two quarter turns put the photo upside down)."""
    return exists().where(
        Job.id == Asset.turning_job_id,
        Job.kind == JOB_KIND,
        Job.status.in_(worker_queue.ACTIVE),
    )


def not_turning() -> ColumnElement[bool]:
    """The opposite of `turning`, for lists."""
    return or_(Asset.turning_job_id.is_(None), ~turning())


def free_to_turn() -> ColumnElement[bool]:
    """The opposite of `turning`, as a claim can check it: a job still invisible to a request
    running at the same time is not finished either, so two requests never take one photo. The
    job is looked up by its id: the table holds every job of the workers too."""
    return or_(
        Asset.turning_job_id.is_(None),
        exists().where(Job.id == Asset.turning_job_id, Job.status.in_(FINISHED)),
    )


async def claim(db: AsyncSession, job: Job, ids: list[UUID]) -> set[UUID]:
    """Gives the photos free to turn to the job (not committed); returns them."""
    claimed = await db.scalars(
        update(Asset)
        .where(Asset.id.in_(ids), free_to_turn())
        .values(turning_job_id=job.id)
        .returning(Asset.id)
        .execution_options(synchronize_session=False)
    )
    return set(claimed)


async def is_turning(db: AsyncSession, asset: Asset) -> bool:
    return bool(await db.scalar(select(Asset.id).where(Asset.id == asset.id, turning())))


def angle_of(edits: list[dict[str, Any]]) -> int:
    """The rotation in the edits of a photo (0: none). Every turn changes it."""
    found = next((e for e in edits if e["action"] == "rotate"), None)
    return int(found["parameters"]["angle"]) % 360 if found else 0


def with_turn(edits: list[dict[str, Any]], turn: int) -> list[dict[str, Any]]:
    """The edits of a photo, turned `turn` degrees clockwise more than it is shown now.

    Immich applies the edits in order and allows one rotation: a new one goes last, an existing
    one takes the turn in. A mirror after the rotation reverses its direction.
    """
    edits = [{"action": e["action"], "parameters": e["parameters"]} for e in edits]
    index = next((i for i, e in enumerate(edits) if e["action"] == "rotate"), None)
    if index is None:
        return (
            [*edits, {"action": "rotate", "parameters": {"angle": turn}}] if turn % 360 else edits
        )
    mirrors = sum(1 for e in edits[index + 1 :] if e["action"] == "mirror")
    sign = -1 if mirrors % 2 else 1
    angle = (edits[index]["parameters"]["angle"] + sign * turn) % 360
    if angle:
        edits[index] = {"action": "rotate", "parameters": {"angle": angle}}
    else:
        del edits[index]
    return edits


async def save_turn(db: AsyncSession, client: ImmichClient, asset: Asset, turn: int) -> bool:
    """Turns the photo in Immich, keeping its other edits. True when Immich made the new
    thumbnails in time: the results of the worker modules are then dropped at once (otherwise the
    next sync does it, D-111)."""
    before = await apply_turn(db, client, asset, turn)
    return asset.id in await await_thumbnails(db, client, {asset: before})


async def apply_turn(
    db: AsyncSession,
    client: ImmichClient,
    asset: Asset,
    turn: int,
    edits: list[dict[str, Any]] | None = None,
) -> str | None:
    """Turns the photo in Immich, keeping its other edits (`edits`: as just read from Immich);
    returns its thumbhash from before, for `await_thumbnails`.

    The answer of the orientation module goes at once: it was about the image before the turn,
    and the list of turned photos must not offer the photo again until the module has looked at
    the new one.
    """
    if asset.type != "IMAGE":
        raise ApiError(422, "rotate_not_supported")
    before = (await client.asset(asset.immich_id)).thumbhash
    if edits is None:
        edits = await client.asset_edits(asset.immich_id)
    edits = with_turn(edits, turn)
    if edits:
        await client.set_asset_edits(asset.immich_id, edits)
    else:
        await client.remove_asset_edits(asset.immich_id)
    asset.is_edited = bool(edits)
    await drop_orientation(db, asset)
    await db.commit()
    return before


async def drop_orientation(db: AsyncSession, asset: Asset) -> None:
    """The answer of the orientation module was about the image before the turn (not committed)."""
    await db.execute(delete(AssetOrientation).where(AssetOrientation.asset_id == asset.id))


async def await_thumbnails(
    db: AsyncSession, client: ImmichClient, before: dict[Asset, str | None]
) -> set[UUID]:
    """Waits until Immich makes the new thumbnails of the turned photos; for those that come in
    time, the results of the worker modules are dropped at once. Returns their ids."""
    waiting = dict(before)
    done: set[UUID] = set()
    for _ in range(THUMBNAIL_ATTEMPTS):
        await asyncio.sleep(THUMBNAIL_POLL_S)
        for asset, thumbhash in list(waiting.items()):
            fresh = await client.asset(asset.immich_id)
            if fresh.thumbhash != thumbhash:
                asset.thumbhash = fresh.thumbhash
                asset.immich_updated_at = fresh.updated_at
                done.add(asset.id)
                del waiting[asset]
        if not waiting:
            break
    if done:
        await worker_queue.forget_results(db, list(done))
        await db.commit()
    return done
