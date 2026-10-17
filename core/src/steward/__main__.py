# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entry point: ``python -m steward`` runs the web server."""

import argparse

import uvicorn

from steward.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="steward")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    args = parser.parse_args()

    uvicorn.run(
        "steward.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=get_settings().log_level,
    )


if __name__ == "__main__":
    main()
