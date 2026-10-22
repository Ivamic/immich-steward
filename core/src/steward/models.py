# SPDX-License-Identifier: AGPL-3.0-or-later
"""ORM models."""

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from pgvector.sqlalchemy import HALFVEC
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
    # Immich's hash of the thumbnails: a new one means a new image for the modules.
    thumbhash: Mapped[str | None] = mapped_column(String(100))
    # Has edits in Immich (rotation, crop): its images are asked for as edited.
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    immich_updated_at: Mapped[datetime]
    # Start time of the sync run that last saw this asset; a full sync removes older rows.
    synced_at: Mapped[datetime]
    # When a sync first saw it, if not in the first sync of the account: a new photo, which
    # automatic runs take before the rest of the library.
    added_at: Mapped[datetime | None]
    # The user's decision about this asset; not touched by sync. See REVIEW_STATUSES.
    review_status: Mapped[str] = mapped_column(String(16), default="new", server_default="new")


# new: waiting for a location; skipped: "come back later"; not_applicable: a location makes no
# sense (screenshot, document scan) and the photo never shows up in the to-do list again.
REVIEW_STATUSES = ("new", "skipped", "not_applicable")


class LocationChange(Base):
    """A location written to Immich by the app; the history behind undo (FR-51)."""

    __tablename__ = "location_change"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset.id", ondelete="CASCADE"), index=True
    )
    # Coordinates in Immich right before the write; None when there were none.
    prev_latitude: Mapped[float | None] = mapped_column(Float)
    prev_longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    # manual, or the id of the module whose suggestion was accepted.
    source: Mapped[str] = mapped_column(String(32))
    # This write added the "estimated" tag, so undoing it removes the tag.
    tag_added: Mapped[bool] = mapped_column(Boolean, default=False)
    # applied | undone
    status: Mapped[str] = mapped_column(String(16), default="applied")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    undone_at: Mapped[datetime | None]


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


class Worker(Base):
    """A process that runs ML modules for the core, possibly on another machine."""

    __tablename__ = "worker"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Chosen by the worker (host name by default); registering again under it reuses the row.
    name: Mapped[str] = mapped_column(String(100), unique=True)
    modules: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    device: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(32))
    registered_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    # False after the worker said goodbye; any later request brings it back.
    online: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Random id of the running worker process (new at every start), to tell two computers that
    # use the same name apart. Workers before 0.2.3 send none.
    instance_id: Mapped[uuid.UUID | None]
    # What the worker says it is doing (`worker_queue.WORKER_STATES`), about which module and
    # since when. Older workers say nothing.
    state: Mapped[str | None] = mapped_column(String(16))
    state_module: Mapped[str | None] = mapped_column(String(32))
    state_since: Mapped[datetime | None]


class ModulePause(Base):
    """A worker module whose background runs are paused: workers get no such jobs, none are
    queued automatically. Runs started by hand still go. `worker_queue.ALL_MODULES` pauses all."""

    __tablename__ = "module_pause"

    module_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    paused_at: Mapped[datetime] = mapped_column(default=utcnow)
    # The pause ends by itself then; None: until resumed.
    until: Mapped[datetime | None]


class Job(Base):
    """Background task: run inside the core (steward.jobs.JobRunner) or leased by a worker."""

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
    # Higher first. Jobs the user waits for are above background ones.
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    # Worker jobs: the module to run and the lease of the worker that took the job.
    module_id: Mapped[str | None] = mapped_column(String(32))
    worker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("worker.id", ondelete="SET NULL")
    )
    lease_until: Mapped[datetime | None]


class ModuleRun(Base):
    """One run of a location module on an asset, and its result."""

    __tablename__ = "module_run"
    __table_args__ = (Index("ix_module_run_asset_module", "asset_id", "module_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("asset.id", ondelete="CASCADE"))
    module_id: Mapped[str] = mapped_column(String(32))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job.id", ondelete="SET NULL"))
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(String(16), default="queued")
    # Reported by the module with the result.
    module_version: Mapped[str | None] = mapped_column(String(32))
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    error: Mapped[str | None] = mapped_column(Text)
    # Part of the photo the run looked at (FR-35): {"x", "y", "w", "h"} as shares of the width
    # and height of the oriented photo; None (SQL NULL) for the whole photo.
    region: Mapped[dict[str, float] | None] = mapped_column(
        JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
    )
    # The photo was turned this many degrees clockwise for the run (shown so in the app; the
    # region, if any, is on the turned photo).
    turn: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Why a failed run failed, one of `worker_queue.FAILURE_CODES` (or a newer worker's code);
    # `error` keeps the details.
    error_code: Mapped[str | None] = mapped_column(String(32))
    worker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("worker.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]


# Length of the vectors of the similar-photos module (MegaLoc, M3).
EMBEDDING_DIM = 8448


class Embedding(Base):
    """Vector of a photo, or of a part of it, computed by a run of a retrieval module (M3).

    One per asset and module for the whole photo (the newest run replaces the older vector), and
    one for the latest part. The search looks among the `located` rows of the user's own photos.
    """

    __tablename__ = "embedding"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("module_run.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[str] = mapped_column(String(32))
    module_version: Mapped[str] = mapped_column(String(32))
    # Vector of a part of the photo (FR-35): never searched among.
    region: Mapped[bool] = mapped_column(Boolean)
    # Whole photo whose asset has a location: kept in step with the asset by
    # `steward.embeddings.refresh_located`.
    located: Mapped[bool] = mapped_column(Boolean)
    vector: Mapped[Any] = mapped_column(HALFVEC(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
