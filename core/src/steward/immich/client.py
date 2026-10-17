# SPDX-License-Identifier: AGPL-3.0-or-later
"""Async HTTP client for Immich."""

from datetime import datetime
from types import TracebackType
from typing import Any, Self
from uuid import UUID

import httpx2
from pydantic import BaseModel

from steward.immich.models import (
    ApiKeyInfo,
    ImmichAlbum,
    ImmichAsset,
    ImmichUser,
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
            base_url=base_url.rstrip("/") + "/api",
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

    async def _get[M: BaseModel](self, path: str, model: type[M]) -> M:
        return model.model_validate(await self._request("GET", path))

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx2.HTTPError as exc:
            raise ImmichUnreachableError(f"{method} {path}: {type(exc).__name__}") from exc
        if response.status_code == 401:
            raise ImmichAuthError(f"{method} {path}: API key rejected")
        if response.status_code == 403:
            raise ImmichPermissionError(f"{method} {path}: {_message(response)}")
        if response.is_error:
            raise ImmichError(f"{method} {path}: HTTP {response.status_code} {_message(response)}")
        return response.json()


def _message(response: httpx2.Response) -> str:
    try:
        return str(response.json().get("message", ""))
    except ValueError:
        return response.text[:200]
