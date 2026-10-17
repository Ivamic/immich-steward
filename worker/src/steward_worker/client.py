# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP client of the worker API of the core (`/api/worker/...`)."""

from dataclasses import asdict, dataclass
from types import TracebackType
from typing import Any, Self
from uuid import UUID

import httpx2

from steward_worker.modules import Candidate

PROTOCOL_VERSION = 1
TIMEOUT_S = 60.0


class CoreError(Exception):
    """The core could not be reached or answered with an unexpected error."""


class WorkerUnknown(CoreError):
    """The core does not know this worker (e.g. its database was reset): register again."""


class LeaseLost(CoreError):
    """The job is no longer ours: its lease ran out and another worker may have it."""


@dataclass(frozen=True)
class LeasedJob:
    job_id: UUID
    module: str
    asset_id: UUID
    attempt: int
    lease_seconds: int


class CoreClient:
    def __init__(
        self, core_url: str, token: str, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self._http = httpx2.AsyncClient(
            base_url=core_url.rstrip("/") + "/api/worker",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT_S,
            transport=transport,
        )
        self.worker_id: UUID | None = None
        self.lease_seconds = 300

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._http.aclose()

    async def register(self, name: str, modules: list[str], device: str, version: str) -> None:
        body = {
            "name": name,
            "modules": modules,
            "device": device,
            "version": version,
            "protocol_version": PROTOCOL_VERSION,
        }
        data = (await self._call("POST", "/register", json=body)).json()
        self.worker_id = UUID(data["worker_id"])
        self.lease_seconds = int(data["lease_seconds"])

    async def lease(self, modules: list[str]) -> LeasedJob | None:
        response = await self._call("POST", "/lease", json={"modules": modules})
        if response.status_code == 204:
            return None
        data = response.json()
        return LeasedJob(
            job_id=UUID(data["job_id"]),
            module=data["module"],
            asset_id=UUID(data["asset_id"]),
            attempt=int(data["attempt"]),
            lease_seconds=int(data["lease_seconds"]),
        )

    async def image(self, job_id: UUID) -> bytes:
        return (await self._call("GET", f"/jobs/{job_id}/image")).content

    async def heartbeat(self, job_id: UUID) -> None:
        await self._call("POST", f"/jobs/{job_id}/heartbeat")

    async def result(self, job_id: UUID, version: str, candidates: list[Candidate]) -> None:
        body = {"module_version": version, "candidates": [asdict(c) for c in candidates]}
        await self._call("POST", f"/jobs/{job_id}/result", json=body)

    async def bye(self) -> None:
        """Tells the core this worker stops, so that it is not shown as available."""
        await self._call("POST", "/bye")

    async def fail(self, job_id: UUID, error: str, retry: bool) -> None:
        await self._call("POST", f"/jobs/{job_id}/fail", json={"error": error, "retry": retry})

    async def _call(self, method: str, path: str, **kwargs: Any) -> httpx2.Response:
        headers = {"X-Worker-Id": str(self.worker_id)} if self.worker_id else {}
        try:
            response = await self._http.request(method, path, headers=headers, **kwargs)
        except httpx2.HTTPError as exc:
            raise CoreError(f"{method} {path}: {type(exc).__name__}") from exc
        if response.is_success:
            return response
        code = _code(response)
        if response.status_code == 401 and code == "worker_unknown":
            raise WorkerUnknown(code)
        if response.status_code == 409 and code == "lease_lost":
            raise LeaseLost(code)
        raise CoreError(f"{method} {path}: HTTP {response.status_code} {code}")


def _code(response: httpx2.Response) -> str:
    try:
        return str(response.json().get("code", ""))
    except ValueError:
        return response.text[:200]
