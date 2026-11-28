# SPDX-License-Identifier: AGPL-3.0-or-later
"""People, animals and vehicles in the photos, and the masks of the details (D-248).

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_objects",
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "run_id", sa.Uuid(), sa.ForeignKey("module_run.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("groups", postgresql.JSONB(), nullable=False),
        sa.Column("found", postgresql.JSONB(), nullable=False),
        sa.Column("labels", sa.LargeBinary(), nullable=False),
        sa.Column("module_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_asset_objects_run", "asset_objects", ["run_id"])
    op.add_column("detail_match", sa.Column("masked", sa.Boolean(), nullable=True))
    op.add_column("detail_match", sa.Column("mask_key", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("detail_match", "mask_key")
    op.drop_column("detail_match", "masked")
    op.drop_index("ix_asset_objects_run", table_name="asset_objects")
    op.drop_table("asset_objects")
