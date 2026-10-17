# SPDX-License-Identifier: AGPL-3.0-or-later
"""ORM models."""

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSON().with_variant(JSONB(), "postgresql"),
    }


class Account(Base):
    """An Immich user who has signed in to the app."""

    __tablename__ = "account"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    immich_user_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    name: Mapped[str]
    email: Mapped[str]
    # Encrypted with steward.crypto.SecretBox; never sent to the browser.
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_login_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Start times of the last successful syncs; incremental syncs continue from `synced_at`.
    synced_at: Mapped[datetime | None]
    full_synced_at: Mapped[datetime | None]


class AuthSession(Base):
    __tablename__ = "auth_session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]


class Asset(Base):
    """Local copy of the Immich asset fields the app works with."""

    __tablename__ = "asset"
    __table_args__ = (
        UniqueConstraint("account_id", "immich_id"),
        Index("ix_asset_account_local_taken_at", "account_id", "local_taken_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    immich_id: Mapped[uuid.UUID]
    type: Mapped[str] = mapped_column(String(16))
    visibility: Mapped[str] = mapped_column(String(16))
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False)
    original_file_name: Mapped[str]
    file_created_at: Mapped[datetime]
    # Wall-clock time of capture without a time zone: what the camera clock showed.
    local_taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    # Absolute capture time, when EXIF has it.
    taken_at: Mapped[datetime | None]
    time_zone: Mapped[str | None] = mapped_column(String(64))
    camera_make: Mapped[str | None]
    camera_model: Mapped[str | None]
    lens_model: Mapped[str | None]
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    city: Mapped[str | None]
    state: Mapped[str | None]
    country: Mapped[str | None]
    checksum: Mapped[str | None]
    immich_updated_at: Mapped[datetime]
    # Start time of the sync run that last saw this asset; a full sync removes older rows.
    synced_at: Mapped[datetime]


class Album(Base):
    __tablename__ = "album"
    __table_args__ = (UniqueConstraint("account_id", "immich_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    immich_id: Mapped[uuid.UUID]
    name: Mapped[str]
    asset_count: Mapped[int] = mapped_column(Integer)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    immich_updated_at: Mapped[datetime]


class AssetAlbum(Base):
    __tablename__ = "asset_album"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
    )
    album_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("album.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Job(Base):
    """Background task; executed by steward.jobs.JobRunner."""

    __tablename__ = "job"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    progress: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
