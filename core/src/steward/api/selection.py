# SPDX-License-Identifier: AGPL-3.0-or-later
"""Actions on several photos chosen in the gallery (D-149): suggestions for them, one location
for all (undone together), skip / not applicable, and turning them in Immich in the background."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from steward import jobs, locations, module_display, selection
from steward.api.assets import (
    CandidateItem,
    ModuleSuggestions,
    TrackPointItem,
    _immich,
    _thresholds,
    _tier,
)
from steward.api.library import JobOut
from steward.deps import (
    CurrentAccount,
    DbDep,
    ImmichFactoryDep,
    SecretBoxDep,
    SettingsDep,
    get_secret_box,
)
from steward.errors import ApiError
from steward.models import Asset, Job
from steward.worker_queue import PRIORITY_USER

router = APIRouter(prefix="/selection")

# Far more than anyone chooses by hand; keeps a request bounded.
MAX_ASSETS = 2000

AssetIds = Annotated[list[UUID], Field(min_length=1, max_length=MAX_ASSETS)]


class SelectionIn(BaseModel):
    ids: AssetIds


class SelectionLocation(BaseModel):
    ids: AssetIds
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # Also the photos that already have a location.
    overwrite: bool = False


class LocationWritten(BaseModel):
    # None when nothing was written (all had a location already).
    batch_id: UUID | None
    written: int
    skipped_located: int


class BatchUndoIn(BaseModel):
    batch_id: UUID


class BatchUndone(BaseModel):
    undone: int
    changed: int
    failed: int


class SelectionReview(BaseModel):
    ids: AssetIds
    status: Literal["new", "skipped", "not_applicable"]


class ReviewChanged(BaseModel):
    changed: int


class SelectionRotate(BaseModel):
    ids: AssetIds
    # Clockwise, on top of how each photo is shown now.
    turn: Literal[90, 180, 270]


async def _own_assets(db: DbDep, account: CurrentAccount, ids: list[UUID]) -> list[Asset]:
    """The chosen photos of the account, in the order of their time."""
    assets = list(
        await db.scalars(
            select(Asset)
            .where(Asset.id.in_(ids), Asset.account_id == account.id)
            .order_by(Asset.local_taken_at, Asset.id)
        )
    )
    if not assets:
        raise ApiError(404, "asset_not_found")
    return assets


@router.post("/suggestions")
async def suggestions(
    body: SelectionIn, account: CurrentAccount, db: DbDep, settings: SettingsDep
) -> list[ModuleSuggestions]:
    """Suggestions from what is already known: no module is run (D-149)."""
    assets = await _own_assets(db, account, body.ids)

    def confident(module_id: str, score: float) -> bool:
        return score >= _thresholds(module_id, settings)[2]

    blocks = await selection.suggest(db, account.id, assets, settings, confident)
    displays = await module_display.get(db, account.id)
    order = {d.module: i for i, d in enumerate(displays)}
    hidden = {d.module for d in displays if d.hidden}
    result = []
    for block in blocks:
        _, weak_below, confident_from = _thresholds(block.module, settings)
        result.append(
            ModuleSuggestions(
                module=block.module,
                version=block.version,
                color=block.color,
                shape=block.shape,
                candidates=[
                    CandidateItem(
                        rank=rank,
                        tier=_tier(c.score, weak_below, confident_from)
                        if block.module not in (selection.SELECTION_ID, "time_neighbors")
                        else "normal",
                        **vars(c),
                    )
                    for rank, c in enumerate(block.result.candidates, start=1)
                ],
                track=[TrackPointItem(**vars(p)) for p in block.result.track],
                cameras=[],
                note=block.result.note,
                key=block.module,
                hidden=block.module in hidden,
            )
        )
    # The chosen photos' own locations first, then the modules in the order of the account.
    return sorted(
        result,
        key=lambda b: -1 if b.module == selection.SELECTION_ID else order.get(b.module, len(order)),
    )


@router.post("/location")
async def set_location(
    body: SelectionLocation,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> LocationWritten:
    """Writes one location to the chosen photos (FR-23); undone together with `/location/undo`."""
    assets = await _own_assets(db, account, body.ids)
    async with _immich(settings, factory, box, account) as client:
        written = await locations.write_batch(
            db,
            client,
            assets,
            body.latitude,
            body.longitude,
            overwrite=body.overwrite,
            tag=settings.estimated_tag,
        )
    return LocationWritten(
        batch_id=written.batch_id,
        written=written.written,
        skipped_located=written.skipped_located,
    )


@router.post("/location/undo")
async def undo_location(
    body: BatchUndoIn,
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
) -> BatchUndone:
    async with _immich(settings, factory, box, account) as client:
        undone = await locations.undo_batch(
            db, client, account.id, body.batch_id, tag=settings.estimated_tag
        )
    return BatchUndone(undone=undone.undone, changed=undone.changed, failed=undone.failed)


@router.put("/review")
async def set_review(body: SelectionReview, account: CurrentAccount, db: DbDep) -> ReviewChanged:
    """Marks the chosen photos as skipped / not applicable, or returns them to the to-do list."""
    assets = await _own_assets(db, account, body.ids)
    changed = [a for a in assets if a.review_status != body.status]
    for asset in changed:
        asset.review_status = body.status
    await db.commit()
    return ReviewChanged(changed=len(changed))


# The job needs Immich and the secret key: without them the request fails at once.
@router.post("/rotate", dependencies=[Depends(get_secret_box)])
async def rotate(body: SelectionRotate, account: CurrentAccount, db: DbDep) -> JobOut:
    """Turns the chosen photos in Immich in the background (videos are left as they are); the
    job tells the progress."""
    assets = await _own_assets(db, account, body.ids)
    job = await jobs.add(
        db,
        jobs.ROTATE,
        account.id,
        {"asset_ids": [str(a.id) for a in assets], "turn": body.turn},
        priority=PRIORITY_USER,
    )
    return JobOut.of(job)


@router.get("/jobs/{job_id}")
async def job(job_id: UUID, account: CurrentAccount, db: DbDep) -> JobOut:
    found = await db.get(Job, job_id)
    if found is None or found.account_id != account.id or found.kind != jobs.ROTATE:
        raise ApiError(404, "job_not_found")
    return JobOut.of(found)
