# SPDX-License-Identifier: AGPL-3.0-or-later
"""immich-steward core service."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("steward")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"
