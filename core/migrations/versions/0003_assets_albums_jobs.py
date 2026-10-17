# SPDX-License-Identifier: AGPL-3.0-or-later
"""Assets, albums and background jobs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("account", sa.Column("synced_at", TZ, nullable=True))
    op.add_column("account", sa.Column("full_synced_at", TZ, nullable=True))

    op.create_table(
        "asset",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("immich_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("is_trashed", sa.Boolean(), nullable=False),
        sa.Column("original_file_name", sa.String(), nullable=False),
        sa.Column("file_created_at", TZ, nullable=False),
        sa.Column("local_taken_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("taken_at", TZ, nullable=True),
        sa.Column("time_zone", sa.String(64), nullable=True),
        sa.Column("camera_make", sa.String(), nullable=True),
        sa.Column("camera_model", sa.String(), nullable=True),
        sa.Column("lens_model", sa.String(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("checksum", sa.String(), nullable=True),
        sa.Column("immich_updated_at", TZ, nullable=False),
        sa.Column("synced_at", TZ, nullable=False),
        sa.UniqueConstraint("account_id", "immich_id"),
    )
    op.create_index("ix_asset_account_local_taken_at", "asset", ["account_id", "local_taken_at"])

    op.create_table(
        "album",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("immich_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("asset_count", sa.Integer(), nullable=False),
        sa.Column("shared", sa.Boolean(), nullable=False),
        sa.Column("immich_updated_at", TZ, nullable=False),
        sa.UniqueConstraint("account_id", "immich_id"),
    )
    op.create_table(
        "asset_album",
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("asset.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "album_id",
            sa.Uuid(),
            sa.ForeignKey("album.id", ondelete="CASCADE"),
            primary_key=True,
            index=True,
        ),
    )

    op.create_table(
        "job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, index=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("progress", JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("started_at", TZ, nullable=True),
        sa.Column("finished_at", TZ, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("job")
    op.drop_table("asset_album")
    op.drop_table("album")
    op.drop_table("asset")
    op.drop_column("account", "full_synced_at")
    op.drop_column("account", "synced_at")
