# SPDX-License-Identifier: AGPL-3.0-or-later
"""Client for the Immich REST API (only the endpoints the app needs)."""

from steward.immich.client import (
    ImmichAuthError,
    ImmichClient,
    ImmichError,
    ImmichPermissionError,
    ImmichUnreachableError,
)
from steward.immich.models import ApiKeyInfo, ImmichUser, ServerVersion

__all__ = [
    "ApiKeyInfo",
    "ImmichAuthError",
    "ImmichClient",
    "ImmichError",
    "ImmichPermissionError",
    "ImmichUnreachableError",
    "ImmichUser",
    "ServerVersion",
]
