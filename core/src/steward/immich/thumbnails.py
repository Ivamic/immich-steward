# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetching thumbnails and previews from Immich through one shared connection pool.

A gallery page requests dozens of images at once; the pool keeps connections alive and caps
the number of parallel requests, so that the app does not overload Immich.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import httpx2

from steward.immich.client import (
    ImmichPermissionError,
    ImmichUnreachableError,
    api_base_url,
    raise_for_status,
)

# fullsize: for web-friendly originals Immich redirects to the original file, which needs the
# optional asset.download permission; without it the preview is returned instead.
ThumbnailSize = Literal["thumbnail", "preview", "fullsize"]

MAX_PARALLEL_REQUESTS = 8
TIMEOUT_S = 30.0


@dataclass(frozen=True)
class Image:
    content: bytes
    media_type: str


class ThumbnailFetcher:
    def __init__(self, server_url: str, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._http = httpx2.AsyncClient(
            base_url=api_base_url(server_url),
            timeout=TIMEOUT_S,
            transport=transport,
            limits=httpx2.Limits(
                max_connections=MAX_PARALLEL_REQUESTS,
                max_keepalive_connections=MAX_PARALLEL_REQUESTS,
            ),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def fetch(self, api_key: str, asset_id: UUID, size: ThumbnailSize) -> Image:
        try:
            return await self._fetch(api_key, asset_id, size)
        except ImmichPermissionError:
            if size != "fullsize":
                raise
            return await self._fetch(api_key, asset_id, "preview")

    async def _fetch(self, api_key: str, asset_id: UUID, size: ThumbnailSize) -> Image:
        path = f"/assets/{asset_id}/thumbnail"
        try:
            response = await self._http.get(
                path,
                params={"size": size},
                headers={"x-api-key": api_key},
                follow_redirects=size == "fullsize",
            )
        except httpx2.HTTPError as exc:
            raise ImmichUnreachableError(f"GET {path}: {type(exc).__name__}") from exc
        raise_for_status(response, f"GET {path}")
        media_type = response.headers.get("content-type", "application/octet-stream")
        return Image(response.content, media_type)
