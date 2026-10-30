# SPDX-License-Identifier: AGPL-3.0-or-later
"""ORM models."""

import uuid
from datetime import UTC, date, datetime
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
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, REAL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSON().with_variant(JSONB(), "postgresql"),
    }


class AppSetting(Base):
    """A setting of the whole installation, not of one account (`steward.updates` and later
    others), stored as JSON."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AccountSetting(Base):
    """A personal setting of an account (`steward.account_settings`), stored as JSON."""

    __tablename__ = "account_setting"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


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
    # The changes of one write to several photos, undone together.
    batch_id: Mapped[uuid.UUID | None] = mapped_column(index=True)


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
    # Modules turned off for this worker on the Processing page: it gets no jobs of them. Kept by
    # its name across restarts.
    disabled_modules: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list, server_default="[]"
    )

    @property
    def enabled_modules(self) -> list[str]:
        """The modules it runs and may get jobs of."""
        return [m for m in self.modules if m not in (self.disabled_modules or [])]


class ModulePause(Base):
    """A worker module whose background runs are paused: workers get no such jobs, none are
    queued automatically. Runs started by hand still go. `worker_queue.ALL_MODULES` pauses all."""

    __tablename__ = "module_pause"

    module_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    paused_at: Mapped[datetime] = mapped_column(default=utcnow)
    # The pause ends by itself then; None: until resumed.
    until: Mapped[datetime | None]


class ModuleDisplay(Base):
    """Where the suggestions of a module stand in the photo card of an account, and whether they
    are shown (`steward.module_display`). Hiding only hides: the module still runs."""

    __tablename__ = "module_display"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    module_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class MapSourceSetting(Base):
    """A satellite imagery source of the map as an account set it up (`steward.map_sources`):
    switched on (= the account agrees to the provider's terms), its API key, the own count of
    tiles and what the provider said about the key."""

    __tablename__ = "map_source_setting"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Encrypted with steward.crypto.SecretBox, like the Immich key.
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    # A token to read the usage from the provider (MapTiler service token); never sent to the
    # browser, used by the core only.
    usage_token_encrypted: Mapped[str | None] = mapped_column(Text)
    # The own count of tiles starts here (reset by hand or on `reset_day` every month).
    counted_since: Mapped[datetime] = mapped_column(default=utcnow)
    # Day of the month the provider starts a new period on; None: reset by hand only.
    reset_day: Mapped[int | None] = mapped_column(Integer)
    # `map_sources.KEY_PROBLEMS`, as the key check or the tiles in the browser saw it.
    key_problem: Mapped[str | None] = mapped_column(String(16))
    key_problem_at: Mapped[datetime | None]
    # The last usage the provider reported (`map_sources.ProviderUsage` fields).
    provider_usage: Mapped[dict[str, Any] | None]


class MapTileUsage(Base):
    """Tiles of a source the browsers of an account loaded, per day (the own count, D-146)."""

    __tablename__ = "map_tile_usage"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    tiles: Mapped[int] = mapped_column(Integer, default=0)


class MapAuto(Base):
    """Which source the map of an account shows far out and close up when switching by itself
    (D-143); whether it switches is kept in the browser."""

    __tablename__ = "map_auto"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    far_source: Mapped[str | None] = mapped_column(String(32))
    near_source: Mapped[str | None] = mapped_column(String(32))
    # The near source shows from this zoom on.
    switch_zoom: Mapped[int] = mapped_column(Integer)


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


class SimilarHint(Base):
    """How similar the most similar photo with a location is, for a photo without one: the
    badge and the filter "similar with a location" of the gallery. Computed in the background
    (`steward.similar_hints`), so the gallery need not search per photo."""

    __tablename__ = "similar_hint"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    similarity: Mapped[float] = mapped_column(Float)
    # Calibrated as the candidates of similar photos are (`modules.similar.calibrated`).
    score: Mapped[float] = mapped_column(Float)
    # The most similar photo; no foreign key: it may go before the next refresh.
    neighbor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    computed_at: Mapped[datetime] = mapped_column(default=utcnow)


class ViewNeighbor(Base):
    """The photos most similar to a photo among all the photos of the account, with or without a
    location (`steward.view_groups`): the graph the groups are built from. Kept, so that new
    thresholds and new locations need no search."""

    __tablename__ = "view_neighbor"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    # Most similar first; no foreign keys: a neighbor may go before the next refresh.
    neighbor_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid))
    similarities: Mapped[list[float]] = mapped_column(ARRAY(REAL))
    computed_at: Mapped[datetime] = mapped_column(default=utcnow)


class ViewGroup(Base):
    """A group of photos of one view (`steward.view_groups`), on a tab of the page "Groups"."""

    __tablename__ = "view_group"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    # The tab: "environment" (similar surroundings, MegaLoc).
    kind: Mapped[str] = mapped_column(String(16))
    # Given by the user; None: not named.
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Photos of the group tell nothing about the place (a pet, documents): never suggested.
    trash: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ViewGroupMember(Base):
    """A photo of a group: found by the rule ("core", "attached"), added by the user ("added"), or
    taken out by the user ("excluded": not in the group, and kept out by the rebuilds)."""

    __tablename__ = "view_group_member"
    __table_args__ = (
        # A photo is in one group at most.
        Index(
            "ux_view_group_member_asset",
            "asset_id",
            unique=True,
            postgresql_where=text("role <> 'excluded'"),
        ),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("view_group.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
