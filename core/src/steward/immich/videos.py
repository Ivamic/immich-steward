# SPDX-License-Identifier: AGPL-3.0-or-later
"""Playing videos from Immich: passed through as a stream, never held in memory.

Immich plays its encoded version when there is one (as in its own web app), otherwise the
original. Byte ranges are passed on both ways, so the browser seeks without downloading the
whole file. Needs the same `asset.view` permission as thumbnails.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import httpx2

from steward.immich.client import (
    ImmichError,
    ImmichUnreachableError,
    api_base_url,
    raise_for_status,
)

# A few players at a time per installation; each holds its connection while it plays.
MAX_PARALLEL_STREAMS = 6
# Waiting for the next part may take long on a slow disk or network, the connection must not.
TIMEOUT = httpx2.Timeout(60.0, connect=10.0)
# What the browser needs of Immich's answer to play and seek.
PASSED_HEADERS = ("content-type", "content-length", "content-range", "accept-ranges", "etag")


@dataclass
class VideoStream:
    status_code: int
    headers: dict[str, str]
    chunks: AsyncIterator[bytes]
    response: httpx2.Response

    async def aclose(self) -> None:
        await self.response.aclose()


class VideoStreamer:
    def __init__(self, server_url: str, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._http = httpx2.AsyncClient(
            base_url=api_base_url(server_url),
            timeout=TIMEOUT,
            transport=transport,
            limits=httpx2.Limits(
                max_connections=MAX_PARALLEL_STREAMS,
                max_keepalive_connections=MAX_PARALLEL_STREAMS,
            ),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def open(self, api_key: str, asset_id: UUID, byte_range: str | None) -> VideoStream:
        """Starts the video, or the requested part of it (`Range` header of the browser)."""
        path = f"/assets/{asset_id}/video/playback"
        headers = {"x-api-key": api_key} | ({"range": byte_range} if byte_range else {})
        request = self._http.build_request("GET", path, headers=headers)
        try:
            response = await self._http.send(request, stream=True)
        except httpx2.ConnectError as exc:
            raise ImmichUnreachableError(f"GET {path}: {type(exc).__name__}") from exc
        except httpx2.HTTPError as exc:
            raise ImmichError(f"GET {path}: {type(exc).__name__}") from exc
        if response.is_error:
            try:
                await response.aread()
            finally:
                await response.aclose()
            raise_for_status(response, f"GET {path}")
        passed = {
            name: response.headers[name] for name in PASSED_HEADERS if name in response.headers
        }
        # The chunks come decoded: a length of the encoded body would no longer fit.
        if "content-encoding" in response.headers:
            passed.pop("content-length", None)
        return VideoStream(response.status_code, passed, response.aiter_bytes(), response)
