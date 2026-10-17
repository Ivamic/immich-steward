# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sign-in with an Immich API key, or with an Immich email and password.

Password sign-in opens a short Immich session only to create an API key for the app (the first
time, or when the stored key stopped working) and closes it right away. The password is never
stored; afterwards the app works with the key, like after a key sign-in.
"""

import hashlib
import logging
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.crypto import SecretBox, hash_token
from steward.errors import ApiError
from steward.immich import (
    ImmichAuthError,
    ImmichClient,
    ImmichError,
    ImmichPermissionError,
    ImmichUnreachableError,
    ImmichUser,
)
from steward.immich.compat import (
    OPTIONAL_PERMISSIONS,
    REQUIRED_PERMISSIONS,
    SUPPORTED_MAJOR_VERSIONS,
    is_supported,
    missing_permissions,
)
from steward.models import Account, AuthSession

log = logging.getLogger(__name__)

KEY_NAME_PREFIX = "immich-steward"
KEY_PROBLEMS = frozenset({"immich_invalid_api_key", "immich_missing_permissions"})


async def verify_api_key(client: ImmichClient) -> ImmichUser:
    """Checks server version and key permissions; returns the key owner."""
    try:
        await _check_version(client)
        key = await client.api_key_info()
        missing = missing_permissions(key.permissions)
        if missing:
            raise ApiError(403, "immich_missing_permissions", permissions=missing)
        return await client.current_user()
    except ImmichUnreachableError as exc:
        raise ApiError(502, "immich_unreachable") from exc
    except ImmichAuthError as exc:
        raise ApiError(401, "immich_invalid_api_key") from exc
    except ImmichPermissionError as exc:
        # The key info said it was fine, but Immich still refused: report as missing permissions.
        raise ApiError(403, "immich_missing_permissions", permissions=[]) from exc


def api_key_name(secret_key: str) -> str:
    """Name of the keys this installation creates; tells installations sharing an Immich apart."""
    tag = hashlib.sha256(b"api-key-name:" + secret_key.encode()).hexdigest()[:8]
    return f"{KEY_NAME_PREFIX} {tag}"


async def password_login(
    db: AsyncSession,
    box: SecretBox,
    client: ImmichClient,
    key_client: Callable[[str], ImmichClient],
    email: str,
    password: str,
    key_name: str,
) -> tuple[ImmichUser, str]:
    """Checks the password with Immich; returns the user and an API key for the app.

    `client` has no key; `key_client(key)` makes a client authenticated with a key.
    """
    try:
        await _check_version(client)
        session = await client.login(email, password)
    except ImmichUnreachableError as exc:
        raise ApiError(502, "immich_unreachable") from exc
    except ImmichAuthError as exc:
        raise ApiError(401, "immich_invalid_credentials") from exc
    except ImmichError as exc:
        # E.g. password sign-in disabled on the server (OAuth only).
        raise ApiError(400, "immich_password_login_failed") from exc

    try:
        stored = await _stored_key(db, box, session.user_id)
        if stored is not None:
            async with key_client(stored) as keyed:
                try:
                    return await verify_api_key(keyed), stored
                except ApiError as exc:
                    # Only a key Immich rejects is replaced, not one hit by a network problem.
                    if exc.code not in KEY_PROBLEMS:
                        raise
                    log.info("Stored API key of %s no longer works; creating a new one", email)
        api_key = await _create_api_key(client, session.access_token, key_name)
        async with key_client(api_key) as keyed:
            return await verify_api_key(keyed), api_key
    except ImmichUnreachableError as exc:
        raise ApiError(502, "immich_unreachable") from exc
    except ImmichError as exc:
        raise ApiError(502, "immich_error") from exc
    finally:
        try:
            await client.logout(session.access_token)
        except ImmichError as exc:
            log.warning("Could not close the Immich session: %s", exc)


async def _check_version(client: ImmichClient) -> None:
    version = await client.server_version()
    if not is_supported(version):
        raise ApiError(
            400,
            "immich_unsupported_version",
            version=str(version),
            supported=sorted(SUPPORTED_MAJOR_VERSIONS),
        )


async def _stored_key(db: AsyncSession, box: SecretBox, immich_user_id: UUID) -> str | None:
    account = await db.scalar(select(Account).where(Account.immich_user_id == immich_user_id))
    if account is None:
        return None
    try:
        return box.decrypt(account.api_key_encrypted)
    except ValueError:  # the secret key of the installation was changed
        return None


async def _create_api_key(client: ImmichClient, access_token: str, name: str) -> str:
    # Keys this installation created earlier are useless: their secrets are lost.
    for key in await client.api_keys(access_token):
        if key.name == name:
            await client.delete_api_key(access_token, key.id)
    permissions = sorted(REQUIRED_PERMISSIONS | OPTIONAL_PERMISSIONS)
    return await client.create_api_key(access_token, name, permissions)


async def sign_in(
    db: AsyncSession, box: SecretBox, user: ImmichUser, api_key: str, ttl: timedelta
) -> tuple[Account, str]:
    """Creates or updates the account and opens a new session. Returns the session token."""
    now = datetime.now(UTC)
    account = await db.scalar(select(Account).where(Account.immich_user_id == user.id))
    if account is None:
        account = Account(immich_user_id=user.id, created_at=now)
        db.add(account)
    account.name = user.name
    account.email = user.email
    account.api_key_encrypted = box.encrypt(api_key)
    account.last_login_at = now
    await db.flush()

    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=hash_token(token), account_id=account.id, expires_at=now + ttl))
    await db.commit()
    return account, token


async def sign_out(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    await db.commit()


# Sessions are extended at most this often, to avoid a database write on every request.
EXTEND_SESSION_AFTER = timedelta(days=1)


async def extend_session(db: AsyncSession, token: str, ttl: timedelta) -> bool:
    """Moves the session end to `ttl` from now (sliding expiry); True when it was moved."""
    session = await db.get(AuthSession, hash_token(token))
    now = datetime.now(UTC)
    if session is None or session.expires_at > now + ttl - EXTEND_SESSION_AFTER:
        return False
    session.expires_at = now + ttl
    await db.commit()
    return True
