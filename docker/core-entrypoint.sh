#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Applies database migrations, then starts the core service.
set -eu

alembic -c /app/alembic.ini upgrade head
exec python -m steward --host 0.0.0.0 --port 8080 "$@"
