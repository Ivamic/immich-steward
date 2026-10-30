# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal settings of the signed-in account (`steward.account_settings`)."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from steward import account_settings, jobs, view_groups
from steward.deps import CurrentAccount, DbDep

router = APIRouter(prefix="/settings")


class AccountSettings(BaseModel):
    gallery_tooltip: bool
    video_sound: bool
    groups_similarity: float
    groups_core_neighbors: int
    groups_mutual: bool


class AccountSettingsIn(BaseModel):
    """Only the settings given change."""

    gallery_tooltip: bool | None = None
    video_sound: bool | None = None
    groups_similarity: float | None = Field(default=None, ge=0.1, le=0.95)
    groups_core_neighbors: int | None = Field(default=None, ge=1, le=view_groups.NEIGHBORS)
    groups_mutual: bool | None = None


@router.get("")
async def get_settings(account: CurrentAccount, db: DbDep) -> AccountSettings:
    return AccountSettings(**await account_settings.get_all(db, account.id))


@router.put("")
async def set_settings(
    body: AccountSettingsIn, account: CurrentAccount, db: DbDep
) -> AccountSettings:
    values = body.model_dump(exclude_none=True)
    before = await account_settings.get_all(db, account.id)
    after = await account_settings.set_many(db, account.id, values)
    if any(before[key] != after[key] for key in account_settings.GROUP_RULE):
        await jobs.enqueue(db, view_groups.JOB_KIND, account.id, {"rebuild": True})
    return AccountSettings(**after)
