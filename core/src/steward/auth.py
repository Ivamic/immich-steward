# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sign-in with an Immich API key."""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.crypto import SecretBox, hash_token
from steward.errors import ApiError
from steward.immich import (
    ImmichAuthError,
    ImmichClient,
    ImmichPermissionError,
    ImmichUnreachableError,
    ImmichUser,
)
from steward.immich.compat import SUPPORTED_MAJOR_VERSIONS, is_supported, missing_permissions
from steward.models import Account, AuthSession


async def verify_api_key(client: ImmichClient) -> ImmichUser:
    """Checks server version and key permissions; returns the key owner."""
    try:
        version = await client.server_version()
        if not is_supported(version):
            raise ApiError(
                400,
                "immich_unsupported_version",
                version=str(version),
                supported=sorted(SUPPORTED_MAJOR_VERSIONS),
            )
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
