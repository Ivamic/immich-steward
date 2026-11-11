# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Immich locked folder of the signed-in account (`steward.locked`)."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from steward import locked
from steward.deps import CurrentAccount, DbDep, ImmichFactoryDep, SecretBoxDep, SettingsDep

router = APIRouter(prefix="/locked")


class LockedState(BaseModel):
    connected: bool
    connected_at: datetime | None
    open: bool
    idle_minutes: int
    blocked_until: datetime | None


class Connected(LockedState):
    # The user has a PIN code in Immich; without one the folder cannot be opened.
    has_pin: bool


class ConnectRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1000)


@router.get("")
async def get_state(account: CurrentAccount, db: DbDep, settings: SettingsDep) -> LockedState:
    return LockedState(**vars(await locked.state(db, account, settings)))


@router.post("/connect")
async def connect(
    body: ConnectRequest,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    factory: ImmichFactoryDep,
    settings: SettingsDep,
) -> Connected:
    has_pin = await locked.connect(db, box, factory, settings, account, body.password)
    return Connected(**vars(await locked.state(db, account, settings)), has_pin=has_pin)


@router.delete("")
async def disconnect(
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    factory: ImmichFactoryDep,
    settings: SettingsDep,
) -> LockedState:
    await locked.disconnect(db, box, factory, settings, account)
    return LockedState(**vars(await locked.state(db, account, settings)))
