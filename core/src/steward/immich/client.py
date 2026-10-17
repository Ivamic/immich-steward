# SPDX-License-Identifier: AGPL-3.0-or-later
"""Async HTTP client for Immich."""

from datetime import datetime
from types import TracebackType
from typing import Any, Self
from uuid import UUID

import httpx2
from pydantic import BaseModel

from steward.immich.models import (
    ApiKey,
    ApiKeyInfo,
    ImmichAlbum,
    ImmichAsset,
    ImmichUser,
    LoginResult,
    SearchPage,
    ServerVersion,
)

DEFAULT_TIMEOUT_S = 30.0
SEARCH_PAGE_SIZE = 1000


class ImmichError(Exception):
    """Base class for errors talking to Immich."""


class ImmichUnreachableError(ImmichError):
    """The server did not answer (wrong URL, network problem, timeout)."""


class ImmichAuthError(ImmichError):
    """The API key was rejected."""


class ImmichPermissionError(ImmichError):
    """The API key lacks a permission required by the endpoint."""


class ImmichClient:
    """Thin wrapper over the Immich REST API. Use as an async context manager."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"x-api-key": api_key} if api_key else {}
        self._http = httpx2.AsyncClient(
            base_url=api_base_url(base_url),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def server_version(self) -> ServerVersion:
        return await self._get("/server/version", ServerVersion)

    async def api_key_info(self) -> ApiKeyInfo:
        return await self._get("/api-keys/me", ApiKeyInfo)

    async def current_user(self) -> ImmichUser:
        return await self._get("/users/me", ImmichUser)

    async def search_assets(
        self,
        *,
        page: int = 1,
        size: int = SEARCH_PAGE_SIZE,
        visibility: str | None = None,
        updated_after: datetime | None = None,
        album_id: UUID | None = None,
        with_exif: bool = True,
        with_deleted: bool = False,
    ) -> SearchPage:
        body: dict[str, Any] = {
            "page": page,
            "size": size,
            "withExif": with_exif,
            "withDeleted": with_deleted,
        }
        if visibility is not None:
            body["visibility"] = visibility
        if updated_after is not None:
            body["updatedAfter"] = updated_after.isoformat()
        if album_id is not None:
            body["albumIds"] = [str(album_id)]
        data = (await self._request("POST", "/search/metadata", json=body))["assets"]
        next_page = data.get("nextPage")
        return SearchPage(
            items=[ImmichAsset.model_validate(item) for item in data["items"]],
            next_page=int(next_page) if next_page else None,
        )

    async def albums(self) -> list[ImmichAlbum]:
        """Albums owned by the user and albums shared with them."""
        owned = await self._request("GET", "/albums")
        shared = await self._request("GET", "/albums", params={"shared": "true"})
        by_id = {album["id"]: album for album in [*owned, *shared]}
        return [ImmichAlbum.model_validate(album) for album in by_id.values()]

    # Password sign-in. The session token is passed explicitly and only lives for one request.

    async def login(self, email: str, password: str) -> LoginResult:
        body = {"email": email, "password": password}
        return LoginResult.model_validate(await self._request("POST", "/auth/login", json=body))

    async def logout(self, access_token: str) -> None:
        await self._request("POST", "/auth/logout", headers=_bearer(access_token))

    async def api_keys(self, access_token: str) -> list[ApiKey]:
        keys = await self._request("GET", "/api-keys", headers=_bearer(access_token))
        return [ApiKey.model_validate(key) for key in keys]

    async def create_api_key(self, access_token: str, name: str, permissions: list[str]) -> str:
        """Returns the secret of the new key; Immich never shows it again."""
        body = {"name": name, "permissions": permissions}
        created = await self._request("POST", "/api-keys", json=body, headers=_bearer(access_token))
        return str(created["secret"])

    async def delete_api_key(self, access_token: str, key_id: UUID) -> None:
        await self._request("DELETE", f"/api-keys/{key_id}", headers=_bearer(access_token))

    async def asset(self, asset_id: UUID) -> ImmichAsset:
        return await self._get(f"/assets/{asset_id}", ImmichAsset)

    async def set_location(self, asset_id: UUID, latitude: float, longitude: float) -> None:
        """Writes coordinates. Immich 3.3 cannot clear them: null is rejected."""
        body = {"latitude": latitude, "longitude": longitude}
        await self._request("PUT", f"/assets/{asset_id}", json=body)

    async def upsert_tag(self, value: str) -> UUID:
        """Id of the tag with this full path ("a/b" is nested); creates the tag if needed."""
        tags = await self._request("PUT", "/tags", json={"tags": [value]})
        return next(UUID(tag["id"]) for tag in tags if tag["value"] == value)

    async def tag_asset(self, tag_id: UUID, asset_id: UUID) -> bool:
        """Adds the tag; False when the asset already had it."""
        return await self._bulk_ids("PUT", f"/tags/{tag_id}/assets", asset_id)

    async def untag_asset(self, tag_id: UUID, asset_id: UUID) -> bool:
        return await self._bulk_ids("DELETE", f"/tags/{tag_id}/assets", asset_id)

    async def _bulk_ids(self, method: str, path: str, asset_id: UUID) -> bool:
        results = await self._request(method, path, json={"ids": [str(asset_id)]})
        return any(r["id"] == str(asset_id) and r["success"] for r in results)

    async def _get[M: BaseModel](self, path: str, model: type[M]) -> M:
        return model.model_validate(await self._request("GET", path))

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx2.HTTPError as exc:
            raise ImmichUnreachableError(f"{method} {path}: {type(exc).__name__}") from exc
        raise_for_status(response, f"{method} {path}")
        if not response.content:
            return None
        return response.json()


def _bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def api_base_url(server_url: str) -> str:
    return server_url.rstrip("/") + "/api"


def raise_for_status(response: httpx2.Response, what: str) -> None:
    if response.status_code == 401:
        raise ImmichAuthError(f"{what}: API key rejected")
    if response.status_code == 403:
        raise ImmichPermissionError(f"{what}: {_message(response)}")
    if response.is_error:
        raise ImmichError(f"{what}: HTTP {response.status_code} {_message(response)}")


def _message(response: httpx2.Response) -> str:
    try:
        return str(response.json().get("message", ""))
    except ValueError:
        return response.text[:200]
