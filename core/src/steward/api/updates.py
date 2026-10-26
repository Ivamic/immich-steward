# SPDX-License-Identifier: AGPL-3.0-or-later
"""Whether a newer release of the app is out, and the switch of the check (`steward.updates`).
The switch is for the whole installation; until there are roles, any account may change it."""

from datetime import datetime
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from steward import __version__, updates
from steward.deps import CurrentAccount, DbDep

router = APIRouter(prefix="/updates")


def get_update_transport(request: Request) -> httpx2.AsyncBaseTransport | None:
    transport: httpx2.AsyncBaseTransport | None = request.app.state.update_transport
    return transport


UpdateTransportDep = Annotated[httpx2.AsyncBaseTransport | None, Depends(get_update_transport)]


class UpdatesOut(BaseModel):
    enabled: bool
    current: str
    latest: str | None
    newer: bool
    # Release notes of the latest release.
    url: str | None
    checked_at: datetime | None
    error: str | None

    @classmethod
    def of(cls, state: updates.UpdateState) -> "UpdatesOut":
        return cls(
            enabled=state.enabled,
            current=__version__,
            latest=state.latest,
            newer=state.newer,
            url=state.url,
            checked_at=state.checked_at,
            error=state.error,
        )


class UpdatesIn(BaseModel):
    enabled: bool


@router.get("")
async def get_updates(_: CurrentAccount, db: DbDep) -> UpdatesOut:
    return UpdatesOut.of(await updates.load(db))


@router.put("")
async def set_updates(
    body: UpdatesIn, _: CurrentAccount, db: DbDep, transport: UpdateTransportDep
) -> UpdatesOut:
    state = await updates.set_enabled(db, body.enabled)
    if state.enabled:
        state = await updates.check_if_due(db, transport)
    return UpdatesOut.of(state)


@router.post("/check")
async def check_now(_: CurrentAccount, db: DbDep, transport: UpdateTransportDep) -> UpdatesOut:
    """Checks at once, also while the automatic check is off."""
    return UpdatesOut.of(await updates.check(db, transport))
