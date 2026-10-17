# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI dependencies shared by the API routers."""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.config import Settings
from steward.crypto import SecretBox, hash_token
from steward.errors import ApiError
from steward.immich import ImmichClient
from steward.models import Account, AuthSession

SESSION_COOKIE = "steward_session"

ImmichClientFactory = Callable[[str, str | None], ImmichClient]


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_immich_factory(request: Request) -> ImmichClientFactory:
    """Creates Immich clients; tests override this to plug in a fake Immich."""
    factory: ImmichClientFactory = request.app.state.immich_factory
    return factory


def get_secret_box(settings: Annotated[Settings, Depends(get_settings)]) -> SecretBox:
    if settings.secret_key is None or settings.immich_url is None:
        raise ApiError(503, "server_not_configured")
    return SecretBox(settings.secret_key.get_secret_value())


async def get_current_account(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Account:
    if not token:
        raise ApiError(401, "not_authenticated")
    account = await db.scalar(
        select(Account)
        .join(AuthSession, AuthSession.account_id == Account.id)
        .where(AuthSession.token_hash == hash_token(token))
        .where(AuthSession.expires_at > datetime.now(UTC))
    )
    if account is None:
        raise ApiError(401, "not_authenticated")
    return account


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
ImmichFactoryDep = Annotated[ImmichClientFactory, Depends(get_immich_factory)]
SecretBoxDep = Annotated[SecretBox, Depends(get_secret_box)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]
