# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP client of the worker API of the core (`/api/worker/...`)."""

import base64
from dataclasses import asdict, dataclass
from types import TracebackType
from typing import Any, Self
from uuid import UUID, uuid4

import httpx2

from steward_worker.modules import Candidate, Embedding

PROTOCOL_VERSION = 1
TIMEOUT_S = 60.0


class CoreError(Exception):
    """The core could not be reached or answered with an unexpected error."""


class WorkerUnknown(CoreError):
    """The core does not know this worker (e.g. its database was reset): register again."""


class CoreRefused(CoreError):
    """The core answered a request with an error (it was reached, unlike a plain CoreError)."""

    # HTTP status of the answer, when known.
    status: int | None = None


class LeaseLost(CoreRefused):
    """The job is no longer ours: its lease ran out and another worker may have it."""


class ImageUnavailable(CoreRefused):
    """The core cannot give the photo of the job; it has recorded why, the job is done with."""


class ImmichUnreachable(CoreRefused):
    """Immich does not answer the core; the job went back to the queue."""


class NameTaken(CoreRefused):
    """Another running worker uses the same name."""


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
        # Tells this process from another computer that uses the same worker name.
        self.instance_id = uuid4()

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
            "instance_id": str(self.instance_id),
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

    async def result(self, job_id: UUID, version: str, output: list[Candidate] | Embedding) -> None:
        body: dict[str, Any] = {"module_version": version, "candidates": []}
        if isinstance(output, Embedding):
            data = base64.b64encode(output.data).decode("ascii")
            body["embedding"] = {"dim": output.dim, "data": data}
        else:
            body["candidates"] = [asdict(c) for c in output]
        await self._call("POST", f"/jobs/{job_id}/result", json=body)

    async def state(self, state: str, module: str | None) -> None:
        """Tells the core what this worker is doing (older cores answer 404)."""
        await self._call("POST", "/state", json={"state": state, "module": module})

    async def bye(self) -> None:
        """Tells the core this worker stops, so that it is not shown as available."""
        await self._call("POST", "/bye")

    async def fail(self, job_id: UUID, error: str, retry: bool, code: str) -> None:
        body = {"error": error, "retry": retry, "code": code}
        await self._call("POST", f"/jobs/{job_id}/fail", json=body)

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
        if response.status_code == 410 and code == "image_unavailable":
            raise ImageUnavailable(_param(response, "reason") or code)
        if response.status_code == 503 and code == "immich_unreachable":
            raise ImmichUnreachable(code)
        if response.status_code == 409 and code == "worker_name_taken":
            raise NameTaken(code)
        error = CoreRefused(f"{method} {path}: HTTP {response.status_code} {code}")
        error.status = response.status_code
        raise error


def _param(response: httpx2.Response, name: str) -> str:
    try:
        return str(response.json().get("params", {}).get(name, ""))
    except (ValueError, AttributeError):
        return ""


def _code(response: httpx2.Response) -> str:
    try:
        return str(response.json().get("code", ""))
    except ValueError:
        return response.text[:200]
