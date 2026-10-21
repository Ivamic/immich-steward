# SPDX-License-Identifier: AGPL-3.0-or-later
"""Saving the turn the user gave a photo in the app to Immich, as an edit (Immich 2.5+).

Immich keeps edits apart from the original file, which stays as it is, and makes new thumbnails
from them. Only called when the user asks for it.
"""

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from steward import worker_queue
from steward.errors import ApiError
from steward.immich import ImmichClient
from steward.models import Asset

# Waiting for Immich to make the new thumbnails: up to 10 s.
THUMBNAIL_POLL_S = 0.5
THUMBNAIL_ATTEMPTS = 20


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
    if asset.type != "IMAGE":
        raise ApiError(422, "rotate_not_supported")
    before = (await client.asset(asset.immich_id)).thumbhash
    edits = with_turn(await client.asset_edits(asset.immich_id), turn)
    if edits:
        await client.set_asset_edits(asset.immich_id, edits)
    else:
        await client.remove_asset_edits(asset.immich_id)
    for _ in range(THUMBNAIL_ATTEMPTS):
        await asyncio.sleep(THUMBNAIL_POLL_S)
        fresh = await client.asset(asset.immich_id)
        if fresh.thumbhash != before:
            await worker_queue.forget_results(db, [asset.id])
            asset.thumbhash = fresh.thumbhash
            asset.immich_updated_at = fresh.updated_at
            await db.commit()
            return True
    return False
