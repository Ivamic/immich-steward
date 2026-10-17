# SPDX-License-Identifier: AGPL-3.0-or-later
"""Supported Immich versions and the API key permissions the app needs."""

from steward.immich.models import ServerVersion

SUPPORTED_MAJOR_VERSIONS = frozenset({3})

REQUIRED_PERMISSIONS = frozenset(
    {
        "user.read",  # who owns the key
        "asset.read",  # asset list, EXIF, search
        "asset.view",  # thumbnails and previews
        "asset.update",  # writing coordinates
        "album.read",  # album filter
        "tag.read",  # tag for estimated coordinates
        "tag.create",
        "tag.asset",
    }
)

# Immich lets a key be created with every permission at once.
ALL_PERMISSIONS = "all"


def is_supported(version: ServerVersion) -> bool:
    return version.major in SUPPORTED_MAJOR_VERSIONS


def missing_permissions(granted: list[str]) -> list[str]:
    if ALL_PERMISSIONS in granted:
        return []
    return sorted(REQUIRED_PERMISSIONS - set(granted))
