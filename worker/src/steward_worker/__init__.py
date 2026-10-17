# SPDX-License-Identifier: AGPL-3.0-or-later
"""Worker of immich-steward: pulls jobs from the core and runs location modules on photos."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("steward-worker")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"
