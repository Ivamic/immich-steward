# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sign-in endpoints."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Response
from pydantic import BaseModel, Field

from steward.auth import sign_in, sign_out, verify_api_key
from steward.deps import (
    SESSION_COOKIE,
    CurrentAccount,
    DbDep,
    ImmichFactoryDep,
    SecretBoxDep,
    SettingsDep,
)
from steward.models import Account

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=200)


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
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )
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
async def me(account: CurrentAccount) -> Me:
    return Me.of(account)
