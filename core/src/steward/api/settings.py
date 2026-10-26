# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal settings of the signed-in account (`steward.account_settings`)."""

from fastapi import APIRouter
from pydantic import BaseModel

from steward import account_settings
from steward.deps import CurrentAccount, DbDep

router = APIRouter(prefix="/settings")


class AccountSettings(BaseModel):
    gallery_tooltip: bool


class AccountSettingsIn(BaseModel):
    """Only the settings given change."""

    gallery_tooltip: bool | None = None


@router.get("")
async def get_settings(account: CurrentAccount, db: DbDep) -> AccountSettings:
    return AccountSettings(**await account_settings.get_all(db, account.id))


@router.put("")
async def set_settings(
    body: AccountSettingsIn, account: CurrentAccount, db: DbDep
) -> AccountSettings:
    values = body.model_dump(exclude_none=True)
    return AccountSettings(**await account_settings.set_many(db, account.id, values))
