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


class OpenRequest(BaseModel):
    pin_code: str = Field(min_length=1, max_length=64)


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


@router.post("/open")
async def open_folder(
    body: OpenRequest,
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    factory: ImmichFactoryDep,
    settings: SettingsDep,
) -> LockedState:
    await locked.open_folder(db, box, factory, settings, account, body.pin_code)
    return LockedState(**vars(await locked.state(db, account, settings)))


@router.post("/close")
async def close_folder(
    account: CurrentAccount,
    db: DbDep,
    box: SecretBoxDep,
    factory: ImmichFactoryDep,
    settings: SettingsDep,
) -> LockedState:
    await locked.close(db, box, factory, settings, account)
    return LockedState(**vars(await locked.state(db, account, settings)))


@router.post("/activity")
async def activity(account: CurrentAccount, db: DbDep, settings: SettingsDep) -> LockedState:
    """A click or key press in the app (sent at most once a minute): keeps an open folder open.
    Background requests of the pages do not, or the folder would never close."""
    await locked.touch(db, account)
    return LockedState(**vars(await locked.state(db, account, settings)))


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
