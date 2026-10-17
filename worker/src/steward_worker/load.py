# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backing off while the machine is busy (e.g. Immich transcodes videos)."""

import os


def system_busy(max_load: float | None) -> bool:
    """True when the 1-minute load average per CPU is above `max_load`.

    Inside a container the load average is the host's, which is what matters here. Platforms
    without a load average (Windows) are never considered busy.
    """
    getloadavg = getattr(os, "getloadavg", None)
    if max_load is None or getloadavg is None:
        return False
    try:
        load1: float = getloadavg()[0]
    except OSError:
        return False
    return load1 / (os.cpu_count() or 1) > max_load
