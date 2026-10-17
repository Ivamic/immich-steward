# SPDX-License-Identifier: AGPL-3.0-or-later
"""History of locations written to Immich.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "location_change",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("asset.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prev_latitude", sa.Float()),
        sa.Column("prev_longitude", sa.Float()),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("tag_added", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_location_change_asset_id", "location_change", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_location_change_asset_id", "location_change")
    op.drop_table("location_change")
