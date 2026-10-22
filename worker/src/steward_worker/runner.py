# SPDX-License-Identifier: AGPL-3.0-or-later
"""Main loop of the worker: register, lease a job, run the module, report, repeat.

The worker only makes outgoing requests, so it can run behind NAT (a laptop) and come and go:
a job it took and never finished returns to the queue when the lease runs out.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from steward_worker import __version__
from steward_worker.client import (
    CoreClient,
    CoreError,
    CoreRefused,
    ImageUnavailable,
    ImmichUnreachable,
    LeasedJob,
    LeaseLost,
    NameTaken,
    WorkerUnknown,
)
from steward_worker.load import system_busy
from steward_worker.modules import Embedding, PermanentError, WorkerModule

log = logging.getLogger(__name__)

# Waiting when there is nothing to do grows from the first value to the second.
IDLE_WAIT_S = (2.0, 30.0)
BUSY_WAIT_S = 30.0
ERROR_WAIT_S = 10.0

# What the worker tells the core it is doing, for the people waiting for it: loading a model
# takes a minute or more on a CPU, and the first start downloads gigabytes.
IDLE = "idle"
BUSY = "busy"
DOWNLOADING = "downloading"
LOADING = "loading"
WORKING = "working"


@dataclass
class WorkerConfig:
    name: str
    device: str = "cpu"
    # Skip leasing while the load average per CPU is above this (None: never).
    max_load: float | None = None
    # Free a model's memory after this long without jobs (NFR-03).
    unload_after_s: float = 600.0
    # Keep one model in memory at a time: another one is loaded only after the current one is
    # freed (for machines short of memory; switching costs a reload).
    one_model: bool = False


class Worker:
    def __init__(
        self,
        client: CoreClient,
        modules: dict[str, WorkerModule],
        config: WorkerConfig,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        busy: Callable[[float | None], bool] = system_busy,
    ) -> None:
        self._client = client
        self._modules = modules
        self._config = config
        self._busy = busy
        self._stop = asyncio.Event()
        self._sleep = sleep or self._interruptible_sleep
        self._loaded: dict[str, float] = {}  # module id -> last use (monotonic)
        self._idle_wait = IDLE_WAIT_S[0]
        self._registered = False
        # The state the core knows; False once the core turned out not to take states.
        self._reported: tuple[str, str | None] | None = None
        self._report_states = True
        self._goodbye: asyncio.Task[None] | None = None

    def stop(self) -> None:
        """Stops after the current job, but says goodbye at once: the core gives the job to
        another worker, and the name is free for a new start even if this process is killed
        before the job ends (Docker waits 10 s; a photo on a slow CPU takes longer)."""
        self._stop.set()
        if self._registered and self._goodbye is None:
            with contextlib.suppress(RuntimeError):  # no event loop: run_forever says it
                self._goodbye = asyncio.get_running_loop().create_task(self._say_goodbye())

    async def run_forever(self) -> None:
        log.info("worker %s with modules %s", self._config.name, ", ".join(self._modules))
        while not self._stop.is_set():
            try:
                worked = await self.run_once()
            except NameTaken:
                log.warning(
                    "another running worker is called %s: give this one a name of its own "
                    "(--name or STEWARD_WORKER_NAME); retrying in %.0f s",
                    self._config.name,
                    ERROR_WAIT_S,
                )
                await self._sleep(ERROR_WAIT_S)
                continue
            except ImmichUnreachable:
                log.warning("the core cannot reach Immich; retrying in %.0f s", ERROR_WAIT_S)
                await self._sleep(ERROR_WAIT_S)
                continue
            except CoreError as exc:
                log.warning("core: %s; retrying in %.0f s", exc, ERROR_WAIT_S)
                await self._sleep(ERROR_WAIT_S)
                continue
            if worked:
                self._idle_wait = IDLE_WAIT_S[0]
            else:
                self._unload_idle()
                await self._sleep(self._idle_wait)
                self._idle_wait = min(self._idle_wait * 2, IDLE_WAIT_S[1])
        self._unload_idle(force=True)
        if self._goodbye is not None:
            await self._goodbye
        elif self._registered:
            await self._say_goodbye()
        if self._registered:
            log.info("stopped")

    async def _say_goodbye(self) -> None:
        with contextlib.suppress(CoreError):
            await self._client.bye()

    async def run_once(self) -> bool:
        """Takes and processes one job; False when there was nothing to do (or no capacity)."""
        if not self._registered:
            await self._register()
        if self._busy(self._config.max_load):
            log.info("system busy, waiting %.0f s", BUSY_WAIT_S)
            await self._report(BUSY)
            await self._sleep(BUSY_WAIT_S)
            return False
        try:
            job = await self._client.lease(list(self._modules))
        except WorkerUnknown:
            self._registered = False
            return True  # register and try again right away
        if job is None:
            await self._report(IDLE)
            return False
        await self._process(job)
        return True

    async def _register(self) -> None:
        await self._client.register(
            self._config.name, list(self._modules), self._config.device, __version__
        )
        self._registered = True
        self._reported = None  # the core forgets the state of a worker that registers
        log.info("registered with the core as %s", self._client.worker_id)

    async def _report(self, state: str, module: str | None = None) -> None:
        """Tells the core what the worker is doing, when that changes. Never fails the work."""
        # After goodbye: any request would show the worker as connected again.
        if not self._report_states or self._stop.is_set() or self._reported == (state, module):
            return
        try:
            await self._client.state(state, module)
        except CoreRefused as exc:
            if exc.status == 404:
                self._report_states = False  # an older core
            else:
                log.warning("cannot tell the core the state: %s", exc)
            return
        except CoreError as exc:
            log.warning("cannot tell the core the state: %s", exc)
            return
        self._reported = (state, module)

    async def _process(self, job: LeasedJob) -> None:
        module = self._modules[job.module]
        log.info(
            "job %s: %s for asset %s (attempt %d)",
            job.job_id,
            job.module,
            job.asset_id,
            job.attempt,
        )
        heartbeat = asyncio.create_task(self._heartbeat(job))
        try:
            image = await self._client.image(job.job_id)
            if job.module not in self._loaded:
                if self._config.one_model:
                    self._unload_idle(force=True)
                cached = getattr(module, "weights_cached", None)
                if cached is not None and not await asyncio.to_thread(cached):
                    log.info("downloading the model of module %s (only the first time)", job.module)
                    await self._report(DOWNLOADING, job.module)
                else:
                    log.info("loading module %s", job.module)
                    await self._report(LOADING, job.module)
                await asyncio.to_thread(module.load)
            self._loaded[job.module] = time.monotonic()
            await self._report(WORKING, job.module)
            started = time.monotonic()
            output = await asyncio.to_thread(module.run, image)
            self._loaded[job.module] = time.monotonic()
            await self._client.result(job.job_id, module.version, output)
            log.info(
                "job %s done in %.1f s: %s",
                job.job_id,
                time.monotonic() - started,
                f"a vector of {output.dim} numbers"
                if isinstance(output, Embedding)
                else f"{len(output)} candidates",
            )
        except LeaseLost:
            log.warning("job %s: lease lost, dropping it", job.job_id)
        except ImageUnavailable as exc:
            log.warning("job %s: the core cannot get the photo from Immich (%s)", job.job_id, exc)
        except ImmichUnreachable:
            raise  # the job is back in the queue; wait before the next one
        except CoreRefused as exc:
            # E.g. the core refused the result: tell it, or the job waits for its lease to end.
            log.warning("job %s: %s", job.job_id, exc)
            with contextlib.suppress(CoreError):
                await self._client.fail(job.job_id, str(exc), retry=True, code="worker_error")
        except CoreError:
            raise
        except Exception as exc:
            log.exception("job %s failed", job.job_id)
            permanent = isinstance(exc, PermanentError)
            with contextlib.suppress(LeaseLost):
                await self._client.fail(
                    job.job_id,
                    f"{type(exc).__name__}: {exc}",
                    retry=not permanent,
                    code="image_invalid" if permanent else "module_error",
                )
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    async def _heartbeat(self, job: LeasedJob) -> None:
        """Extends the lease while the module works (a slow CPU may need longer than one)."""
        while True:
            await asyncio.sleep(job.lease_seconds / 3)
            try:
                await self._client.heartbeat(job.job_id)
            except CoreError as exc:
                log.warning("job %s: heartbeat failed: %s", job.job_id, exc)

    def _unload_idle(self, force: bool = False) -> None:
        now = time.monotonic()
        for module_id, last_used in list(self._loaded.items()):
            if force or now - last_used > self._config.unload_after_s:
                log.info("unloading module %s", module_id)
                self._modules[module_id].unload()
                del self._loaded[module_id]

    async def _interruptible_sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
