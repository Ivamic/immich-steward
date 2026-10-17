# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sign-in endpoints."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Response
from pydantic import BaseModel, Field

from steward.auth import (
    api_key_name,
    extend_session,
    password_login,
    sign_in,
    sign_out,
    verify_api_key,
)
from steward.deps import (
    SESSION_COOKIE,
    CurrentAccount,
    DbDep,
    ImmichFactoryDep,
    SecretBoxDep,
    SettingsDep,
    set_session_cookie,
)
from steward.models import Account

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=200)


class PasswordLoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1000)


class Me(BaseModel):
    id: UUID
    name: str
    email: str

    @classmethod
    def of(cls, account: Account) -> "Me":
        return cls(id=account.id, name=account.name, email=account.email)


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    settings: SettingsDep,
    db: DbDep,
    box: SecretBoxDep,
    immich_factory: ImmichFactoryDep,
) -> Me:
    assert settings.immich_url is not None  # guaranteed by SecretBoxDep
    api_key = body.api_key.strip()
    async with immich_factory(settings.immich_url, api_key) as client:
        user = await verify_api_key(client)
    ttl = timedelta(days=settings.session_ttl_days)
    account, token = await sign_in(db, box, user, api_key, ttl)
    set_session_cookie(response, token, settings)
    return Me.of(account)


@router.post("/login/password")
async def login_with_password(
    body: PasswordLoginRequest,
    response: Response,
    settings: SettingsDep,
    db: DbDep,
    box: SecretBoxDep,
    immich_factory: ImmichFactoryDep,
) -> Me:
    """Signs in with the Immich email and password; the app keeps an API key, not the password."""
    url = settings.immich_url
    assert url is not None and settings.secret_key is not None  # guaranteed by SecretBoxDep
    async with immich_factory(url, None) as client:
        user, api_key = await password_login(
            db,
            box,
            client,
            lambda key: immich_factory(url, key),
            body.email.strip(),
            body.password,
            api_key_name(settings.secret_key.get_secret_value()),
        )
    ttl = timedelta(days=settings.session_ttl_days)
    account, token = await sign_in(db, box, user, api_key, ttl)
    set_session_cookie(response, token, settings)
    return Me.of(account)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    db: DbDep,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    if token:
        await sign_out(db, token)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
async def me(
    account: CurrentAccount,
    response: Response,
    settings: SettingsDep,
    db: DbDep,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Me:
    """The UI asks this on every start, which also keeps the session alive."""
    assert token is not None  # guaranteed by CurrentAccount
    if await extend_session(db, token, timedelta(days=settings.session_ttl_days)):
        set_session_cookie(response, token, settings)
    return Me.of(account)
