# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entry point: ``python -m steward_worker`` (or ``steward-worker``).

Settings come from the command line or from STEWARD_* environment variables. The token is read
only from the environment, so that it does not show up in the process list.
"""

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import socket
import sys

from steward_worker.client import CoreClient
from steward_worker.modules import AVAILABLE, ModuleOptions
from steward_worker.modules.geoclip import resolve_device
from steward_worker.runner import Worker, WorkerConfig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    env = os.environ.get
    max_load = env("STEWARD_WORKER_MAX_LOAD")
    parser = argparse.ArgumentParser(
        prog="steward-worker",
        description="Runs location modules (ML models) for an immich-steward core. "
        "The token is read from STEWARD_WORKER_TOKEN.",
    )
    parser.add_argument(
        "--core",
        default=env("STEWARD_CORE_URL"),
        help="address of the immich-steward core, e.g. http://192.168.1.10:8780 (STEWARD_CORE_URL)",
    )
    parser.add_argument(
        "--modules",
        default=env("STEWARD_WORKER_MODULES", ",".join(AVAILABLE)),
        help=f"comma-separated modules to run (STEWARD_WORKER_MODULES); available: "
        f"{', '.join(AVAILABLE) or 'none yet'}",
    )
    parser.add_argument(
        "--name",
        default=env("STEWARD_WORKER_NAME", socket.gethostname()),
        help="name shown in the core (STEWARD_WORKER_NAME, default: host name)",
    )
    parser.add_argument(
        "--max-load",
        type=float,
        default=float(max_load) if max_load else None,
        help="do not take jobs while the 1-minute load average per CPU is above this, "
        "e.g. 0.8 (STEWARD_WORKER_MAX_LOAD; Linux only)",
    )
    parser.add_argument(
        "--unload-after",
        type=float,
        default=float(env("STEWARD_WORKER_UNLOAD_AFTER_MINUTES", "10")),
        help="free model memory after this many idle minutes (STEWARD_WORKER_UNLOAD_AFTER_MINUTES)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(env("STEWARD_WORKER_THREADS", "2")),
        help="CPU threads for the models (STEWARD_WORKER_THREADS); keep it low on a server "
        "shared with Immich",
    )
    parser.add_argument(
        "--device",
        default=env("STEWARD_WORKER_DEVICE", "auto"),
        choices=["auto", "cpu", "cuda"],
        help="where models run (STEWARD_WORKER_DEVICE); auto picks an NVIDIA GPU when available",
    )
    parser.add_argument("--log-level", default=env("STEWARD_LOG_LEVEL", "info"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # Every HTTP request would be logged at the info level otherwise.
    for noisy in ("httpx", "httpx2", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, logging.getLogger().level))
    token = os.environ.get("STEWARD_WORKER_TOKEN", "")
    modules = [m.strip() for m in args.modules.split(",") if m.strip()]
    unknown = [m for m in modules if m not in AVAILABLE]
    if not args.core or not token or not modules or unknown:
        sys.exit(
            "Set the core address (--core / STEWARD_CORE_URL), STEWARD_WORKER_TOKEN and at least "
            f"one module. Unknown modules: {', '.join(unknown) or 'none'}; "
            f"available: {', '.join(AVAILABLE) or 'none yet'}."
        )
    options = ModuleOptions(threads=args.threads, device=resolve_device(args.device))
    config = WorkerConfig(
        name=args.name,
        device=options.device,
        max_load=args.max_load,
        unload_after_s=args.unload_after * 60,
    )
    asyncio.run(_run(args.core, token, modules, options, config))


async def _run(
    core: str, token: str, module_ids: list[str], options: ModuleOptions, config: WorkerConfig
) -> None:
    async with CoreClient(core, token) as client:
        worker = Worker(client, {m: AVAILABLE[m](options) for m in module_ids}, config)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Windows has no signal handlers in asyncio: Ctrl+C raises KeyboardInterrupt instead.
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, worker.stop)
        try:
            await worker.run_forever()
        except asyncio.CancelledError:
            worker.stop()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
