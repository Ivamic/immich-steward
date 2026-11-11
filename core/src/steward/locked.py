# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Immich locked folder of an account (D-216, D-220).

An API key never opens the locked folder, so the user connects an Immich session once with
their password: the app keeps the session token (encrypted, like the API key), never the
password. The session is seen and can be revoked in Immich (account settings, devices). It is
used for the locked photos only: with the folder open, any search of the session returns them.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from steward.config import Settings
from steward.crypto import SecretBox
from steward.deps import ImmichClientFactory
from steward.errors import ApiError
from steward.immich import (
    ImmichAuthError,
    ImmichClient,
    ImmichError,
    ImmichUnreachableError,
)
from steward.models import Account, LockedFolder

log = logging.getLogger(__name__)


@dataclass
class LockedState:
    connected: bool
    connected_at: datetime | None
    open: bool
    # Minutes without a click or key press in the app that close the folder.
    idle_minutes: int
    # Too many wrong PIN codes: no new try before this.
    blocked_until: datetime | None


async def state(db: AsyncSession, account: Account, settings: Settings) -> LockedState:
    """From the database only: showing the state asks nothing of Immich."""
    folder = await db.get(LockedFolder, account.id)
    return LockedState(
        connected=folder is not None,
        connected_at=folder.connected_at if folder else None,
        open=bool(folder and folder.opened_at),
        idle_minutes=settings.locked_idle_minutes,
        blocked_until=folder.blocked_until if folder else None,
    )


async def connect(
    db: AsyncSession,
    box: SecretBox,
    factory: ImmichClientFactory,
    settings: Settings,
    account: Account,
    password: str,
) -> bool:
    """Signs in to Immich as the account's user and keeps the session; returns whether the user
    has a PIN code in Immich (without one the folder cannot be opened)."""
    assert settings.immich_url is not None  # guaranteed by SecretBoxDep
    try:
        async with factory(settings.immich_url) as client:
            token = (await client.login(account.email, password)).access_token
    except ImmichUnreachableError as exc:
        raise ApiError(502, "immich_unreachable") from exc
    except ImmichAuthError as exc:
        raise ApiError(401, "locked_wrong_password") from exc
    except ImmichError as exc:
        # Password sign-in turned off on the server (OAuth only).
        raise ApiError(400, "locked_password_login_failed") from exc

    try:
        async with factory(settings.immich_url, session_token=token) as session:
            user = await session.current_user()
            if user.id != account.immich_user_id:
                await _end(session)
                raise ApiError(400, "locked_other_user")
            has_pin = (await session.auth_status()).pin_code
    except ImmichUnreachableError as exc:
        raise ApiError(502, "immich_unreachable") from exc
    except ImmichError as exc:
        raise ApiError(502, "immich_error") from exc

    await disconnect(db, box, factory, settings, account, commit=False)
    db.add(LockedFolder(account_id=account.id, session_encrypted=box.encrypt(token)))
    await db.commit()
    return has_pin


async def disconnect(
    db: AsyncSession,
    box: SecretBox,
    factory: ImmichClientFactory,
    settings: Settings,
    account: Account,
    *,
    commit: bool = True,
) -> None:
    """Closes the folder and ends the session in Immich (as far as Immich answers), and forgets
    it."""
    folder = await db.get(LockedFolder, account.id)
    if folder is None:
        return
    assert settings.immich_url is not None
    token = box.decrypt(folder.session_encrypted)
    async with factory(settings.immich_url, session_token=token) as session:
        await _end(session)
    await db.delete(folder)
    if commit:
        await db.commit()


async def _end(session: ImmichClient) -> None:
    try:
        await session.lock_session()
        await session.logout_session()
    except ImmichError as exc:
        # Already ended in Immich (password changed, device removed) or Immich is down: the
        # session is forgotten here anyway.
        log.info("Could not end the Immich session of the locked folder: %s", exc)
