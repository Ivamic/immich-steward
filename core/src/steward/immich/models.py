# SPDX-License-Identifier: AGPL-3.0-or-later
"""Response models for the subset of the Immich API we use. Unknown fields are ignored."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ImmichModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class ServerVersion(ImmichModel):
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class ApiKeyInfo(ImmichModel):
    id: UUID
    name: str
    permissions: list[str]


class ImmichUser(ImmichModel):
    id: UUID
    name: str
    email: str
    is_admin: bool = False


class LoginResult(ImmichModel):
    """A short-lived Immich session; the app only uses it to manage API keys."""

    access_token: str
    user_id: UUID


class ApiKey(ImmichModel):
    id: UUID
    name: str


class ExifInfo(ImmichModel):
    date_time_original: datetime | None = None
    time_zone: str | None = None
    make: str | None = None
    model: str | None = None
    lens_model: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None


class ImmichAsset(ImmichModel):
    id: UUID
    owner_id: UUID
    type: str  # IMAGE | VIDEO | AUDIO | OTHER
    visibility: str  # timeline | archive | hidden | locked
    original_file_name: str
    file_created_at: datetime
    # Local wall-clock time of capture, serialized by Immich with a meaningless "Z".
    local_date_time: datetime
    updated_at: datetime
    is_trashed: bool = False
    width: int | None = None
    height: int | None = None
    checksum: str | None = None
    # Hash of the thumbnails; changes when Immich makes new ones (photo rotated or edited).
    thumbhash: str | None = None
    # The photo has edits in Immich (rotation, crop): its images must be asked for edited.
    is_edited: bool = False
    exif_info: ExifInfo | None = None


class SearchPage(BaseModel):
    items: list[ImmichAsset]
    next_page: int | None


class ImmichAlbum(ImmichModel):
    id: UUID
    album_name: str
    asset_count: int
    updated_at: datetime
    shared: bool = False
