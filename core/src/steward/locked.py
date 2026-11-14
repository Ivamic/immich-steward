# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Immich locked folder of an account (D-216, D-220).

An API key never opens the locked folder, so the user connects an Immich session once with
their password: the app keeps the session token (encrypted, like the API key), never the
password. The session is seen and can be revoked in Immich (account settings, devices). It is
used for the locked photos only: with the folder open, any search of the session returns them.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, delete, exists, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.config import Settings
from steward.crypto import SecretBox
from steward.deps import ImmichClientFactory
from steward.errors import ApiError
from steward.immich import (
    ImmichAuthError,
    ImmichClient,
    ImmichError,
    ImmichPinError,
    ImmichUnreachableError,
)
from steward.models import Account, Asset, AuthSession, Job, LockedFolder, ModuleRun

log = logging.getLogger(__name__)

# Immich does not limit wrong PIN codes; the app allows this many in a row, then a pause.
PIN_TRIES = 5
PIN_PAUSE = timedelta(minutes=5)
# The folder never stays open longer than this without a user action, even while its photos
# are being processed.
MAX_IDLE = timedelta(hours=1)
# Immich closes the folder 15 minutes after the PIN code unless the session is used in its last
# 5 minutes; while open here, the app uses it this often.
KEEP_OPEN_EVERY = timedelta(minutes=4)
# Visibilities of the photos read through the folder (`steward.sync`).
LOCKED_VISIBILITIES = ("locked", "missing")


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
    # Without the folder its photos can be neither shown nor processed: they are forgotten.
    await db.execute(
        delete(Asset).where(
            Asset.account_id == account.id, Asset.visibility.in_(LOCKED_VISIBILITIES)
        )
    )
    await db.delete(folder)
    if commit:
        await db.commit()


def _session(
    box: SecretBox, factory: ImmichClientFactory, settings: Settings, folder: LockedFolder
) -> ImmichClient:
    assert settings.immich_url is not None  # guaranteed by SecretBoxDep
    return factory(settings.immich_url, session_token=box.decrypt(folder.session_encrypted))


async def _connected(db: AsyncSession, account: Account) -> LockedFolder:
    folder = await db.get(LockedFolder, account.id)
    if folder is None:
        raise ApiError(409, "locked_not_connected")
    return folder


async def _session_lost(db: AsyncSession, folder: LockedFolder) -> ApiError:
    """Immich ended the session (password changed, device removed): connect again."""
    await db.delete(folder)
    await db.commit()
    return ApiError(409, "locked_session_lost")


async def open_folder(
    db: AsyncSession,
    box: SecretBox,
    factory: ImmichClientFactory,
    settings: Settings,
    account: Account,
    pin_code: str,
) -> None:
    """Opens the locked folder with the PIN code, which goes to Immich and nowhere else (it is
    neither stored nor logged)."""
    folder = await _connected(db, account)
    now = datetime.now(UTC)
    if folder.blocked_until and folder.blocked_until > now:
        raise ApiError(429, "locked_pin_paused", until=folder.blocked_until.isoformat())
    try:
        async with _session(box, factory, settings, folder) as session:
            await session.unlock_session(pin_code)
    except ImmichPinError as exc:
        if exc.no_pin:
            raise ApiError(400, "locked_no_pin") from exc
        folder.failed_pins += 1
        left = PIN_TRIES - folder.failed_pins
        if left > 0:
            await db.commit()
            raise ApiError(400, "locked_wrong_pin", left=left) from exc
        folder.failed_pins = 0
        until = folder.blocked_until = now + PIN_PAUSE
        await db.commit()
        raise ApiError(429, "locked_pin_paused", until=until.isoformat()) from exc
    except ImmichAuthError as exc:
        raise await _session_lost(db, folder) from exc
    except ImmichUnreachableError as exc:
        raise ApiError(502, "immich_unreachable") from exc
    except ImmichError as exc:
        raise ApiError(502, "immich_error") from exc
    folder.opened_at = folder.active_at = now
    folder.failed_pins = 0
    folder.blocked_until = None
    # The next sync reads all the locked photos: some may have left the folder meanwhile.
    folder.synced_at = None
    await db.commit()
    from steward import jobs  # jobs imports this module

    await jobs.enqueue(db, jobs.SYNC, account.id)


async def close_folder(
    db: AsyncSession,
    box: SecretBox,
    factory: ImmichClientFactory,
    settings: Settings,
    folder: LockedFolder,
) -> None:
    """Closes the folder in Immich too; closed here even when Immich does not answer (Immich
    closes it by itself 15 minutes after the last use of the session)."""
    if folder.opened_at is not None:
        try:
            async with _session(box, factory, settings, folder) as session:
                await session.lock_session()
        except ImmichError as exc:
            log.info("Could not close the locked folder in Immich: %s", exc)
    folder.opened_at = folder.active_at = None
    await db.commit()


async def close(
    db: AsyncSession,
    box: SecretBox,
    factory: ImmichClientFactory,
    settings: Settings,
    account: Account,
) -> None:
    await close_folder(db, box, factory, settings, await _connected(db, account))


async def touch(db: AsyncSession, account: Account) -> None:
    """A click or key press of the user in the app: keeps an open folder open."""
    folder = await db.get(LockedFolder, account.id)
    if folder is not None and folder.opened_at is not None:
        folder.active_at = datetime.now(UTC)
        await db.commit()


async def close_on_sign_out(
    db: AsyncSession,
    box: SecretBox,
    factory: ImmichClientFactory,
    settings: Settings,
    token_hash: str,
) -> None:
    """Signing out of the app closes the folder of that account."""
    account_id = await db.scalar(
        select(AuthSession.account_id).where(AuthSession.token_hash == token_hash)
    )
    folder = await db.get(LockedFolder, account_id) if account_id else None
    if folder is not None and folder.opened_at is not None:
        await close_folder(db, box, factory, settings, folder)


async def close_idle(
    db: AsyncSession, box: SecretBox, factory: ImmichClientFactory, settings: Settings
) -> list[UUID]:
    """Closes the folders without a user action for `locked_idle_minutes`; returns the
    accounts whose folder closed."""
    now = datetime.now(UTC)
    due = now - timedelta(minutes=settings.locked_idle_minutes)
    # Not while workers have its photos (up to an hour without a user action).
    processing = exists(
        select(literal(1))
        .select_from(Job)
        .join(ModuleRun, ModuleRun.job_id == Job.id)
        .join(Asset, Asset.id == ModuleRun.asset_id)
        .where(
            Asset.account_id == LockedFolder.account_id,
            Asset.visibility.in_(LOCKED_VISIBILITIES),
            Job.status.in_(("queued", "running")),
        )
    )
    folders = (
        await db.scalars(
            select(LockedFolder).where(
                LockedFolder.opened_at.is_not(None),
                LockedFolder.active_at < due,
                or_(LockedFolder.active_at < now - MAX_IDLE, ~processing),
            )
        )
    ).all()
    closed = []
    for folder in folders:
        await close_folder(db, box, factory, settings, folder)
        closed.append(folder.account_id)
    return closed


async def open_session(
    db: AsyncSession,
    box: SecretBox,
    factory: ImmichClientFactory,
    settings: Settings,
    account_id: UUID,
) -> tuple[LockedFolder, ImmichClient] | None:
    """The folder and a client of its session, if the folder is open here and in Immich; a
    folder Immich closed (or a session it ended) is closed here too. The caller closes the
    client."""
    folder = await db.get(LockedFolder, account_id)
    if folder is None or folder.opened_at is None:
        return None
    session = _session(box, factory, settings, folder)
    try:
        if (await session.auth_status()).is_elevated:
            return folder, session
    except ImmichUnreachableError:
        await session.aclose()
        raise
    except ImmichError as exc:
        log.info("The session of the locked folder no longer works: %s", exc)
    await session.aclose()
    folder.opened_at = folder.active_at = None
    await db.commit()
    return None


async def keep_open(
    db: AsyncSession, box: SecretBox, factory: ImmichClientFactory, settings: Settings
) -> None:
    """Uses the session of every open folder, so that Immich keeps it open as long as the app
    does (`KEEP_OPEN_EVERY`, called by the job runner)."""
    ids = await db.scalars(
        select(LockedFolder.account_id).where(LockedFolder.opened_at.is_not(None))
    )
    for account_id in ids.all():
        try:
            opened = await open_session(db, box, factory, settings, account_id)
        except ImmichUnreachableError:
            continue
        if opened is not None:
            await opened[1].aclose()


def is_locked(asset: Asset) -> bool:
    return asset.visibility in LOCKED_VISIBILITIES


def folder_open() -> ColumnElement[bool]:
    """The photo's account has its locked folder open (correlated with `Asset`)."""
    return exists(
        select(literal(1)).where(
            LockedFolder.account_id == Asset.account_id, LockedFolder.opened_at.is_not(None)
        )
    )


def shown(*, archive: bool = True) -> ColumnElement[bool]:
    """Photos that may be shown now: the timeline (and the archive), and the locked photos
    while the folder is open. Never the "missing" ones (`steward.sync.MISSING`)."""
    visible = ("timeline", "archive") if archive else ("timeline",)
    return or_(Asset.visibility.in_(visible), and_(Asset.visibility == "locked", folder_open()))


async def check_shown(db: AsyncSession, asset: Asset) -> None:
    """A locked photo is reached only while the folder is open; a "missing" one never."""
    if asset.visibility == "missing":
        raise ApiError(404, "asset_not_found")
    if asset.visibility == "locked":
        folder = await db.get(LockedFolder, asset.account_id)
        if folder is None or folder.opened_at is None:
            raise ApiError(423, "locked_closed")


async def mask_sources(db: AsyncSession, account: Account, blocks: list[Any]) -> None:
    """Locked photos help with suggestions whether the folder is open or not (D-216), but while
    it is closed (and "missing" photos always) a hint names no such photo: in the evidence and
    the route of the suggestions, each item about one gets `locked` and no file name, and the
    page shows a lock instead of its preview."""
    items: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if "asset_id" in value:
                items.append(value)
            for inner in value.values():
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)

    for block in blocks:
        for candidate in block.candidates:
            walk(candidate.evidence)
        for point in block.track:
            items.append(vars(point))
    ids = {UUID(str(item["asset_id"])) for item in items if item.get("asset_id")}
    if not ids:
        return
    folder = await db.get(LockedFolder, account.id)
    hidden_visibilities = ("missing",) if folder and folder.opened_at else LOCKED_VISIBILITIES
    hidden = {
        str(asset_id)
        for asset_id in await db.scalars(
            select(Asset.id).where(Asset.id.in_(ids), Asset.visibility.in_(hidden_visibilities))
        )
    }
    for item in items:
        if str(item.get("asset_id")) in hidden:
            item["locked"] = True
            if "file_name" in item:
                item["file_name"] = ""
    for block in blocks:
        for point in block.track:
            if str(point.asset_id) in hidden:
                point.locked = True
                point.file_name = ""


async def image_session(db: AsyncSession, box: SecretBox, asset: Asset) -> str | None:
    """The session token to get a locked photo's images with, while the folder is open; None for
    the other photos (the API key). A locked photo of a closed folder is refused."""
    if not is_locked(asset):
        return None
    folder = await db.get(LockedFolder, asset.account_id)
    if folder is None or folder.opened_at is None:
        raise ApiError(423, "locked_closed")
    return box.decrypt(folder.session_encrypted)


async def client_for(
    db: AsyncSession,
    box: SecretBox,
    factory: ImmichClientFactory,
    settings: Settings,
    account: Account,
    assets: Iterable[Asset] = (),
) -> ImmichClient:
    """An Immich client to change these photos with: the API key, or the session when one of
    them is locked (the session reaches the others too), only while the folder is open."""
    assert settings.immich_url is not None  # guaranteed by SecretBoxDep
    if any(is_locked(asset) for asset in assets):
        folder = await db.get(LockedFolder, account.id)
        if folder is None or folder.opened_at is None:
            raise ApiError(423, "locked_closed")
        return _session(box, factory, settings, folder)
    return factory(settings.immich_url, box.decrypt(account.api_key_encrypted))


async def hide_if_gone(
    db: AsyncSession,
    box: SecretBox,
    factory: ImmichClientFactory,
    settings: Settings,
    account: Account,
    asset: Asset,
) -> bool:
    """Immich refused an image of a photo the app takes for a timeline one: if the API key no
    longer reaches the photo at all, it was moved into the locked folder or deleted in Immich
    since the last sync, which cannot see either (D-221). It is hidden as "missing" until a sync
    tells which; returns whether it was."""
    if is_locked(asset):
        return False
    assert settings.immich_url is not None  # guaranteed by SecretBoxDep
    try:
        async with factory(settings.immich_url, box.decrypt(account.api_key_encrypted)) as client:
            await client.asset(asset.immich_id)
    except ImmichError as exc:
        if exc.status not in (400, 404):
            return False
        asset.visibility = "missing"
        await db.commit()
        return True
    return False


async def _end(session: ImmichClient) -> None:
    try:
        await session.lock_session()
        await session.logout_session()
    except ImmichError as exc:
        # Already ended in Immich (password changed, device removed) or Immich is down: the
        # session is forgotten here anyway.
        log.info("Could not end the Immich session of the locked folder: %s", exc)
