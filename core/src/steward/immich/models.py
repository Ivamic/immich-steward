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


class AuthStatus(ImmichModel):
    """What Immich says about a session: whether the user has a PIN code and whether the
    session has the locked folder open ("elevated") now, and until when."""

    pin_code: bool
    password: bool
    is_elevated: bool
    pin_expires_at: datetime | None = None


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


class AlbumUserRef(ImmichModel):
    id: UUID


class AlbumUser(ImmichModel):
    user: AlbumUserRef
    role: str  # owner | editor | viewer


class ImmichAlbum(ImmichModel):
    id: UUID
    album_name: str
    asset_count: int
    updated_at: datetime
    shared: bool = False
    album_thumbnail_asset_id: UUID | None = None
    # Taken times of the earliest and the latest asset; none in an empty album.
    start_date: datetime | None = None
    end_date: datetime | None = None
    # The owner first, then the signed-in user if it is someone else, then the rest.
    album_users: list[AlbumUser] = []

    def role_of(self, user_id: UUID) -> str | None:
        """owner | editor | viewer; the owner when Immich lists nobody (not seen in 3.x)."""
        if not self.album_users:
            return "owner"
        return next((u.role for u in self.album_users if u.user.id == user_id), None)


class BulkResult(ImmichModel):
    """Immich's answer for one id of a bulk request."""

    id: UUID
    success: bool
    # duplicate | no_permission | not_found | unknown | validation
    error: str | None = None
