# SPDX-License-Identifier: AGPL-3.0-or-later
"""How well two photos match point by point: the answers of the `details` module (D-225).

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "detail_match",
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "other_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("matches", sa.Integer(), nullable=False),
        sa.Column("inliers", sa.Integer(), nullable=False),
        sa.Column("lines", postgresql.JSONB(), nullable=False),
        sa.Column("module_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_detail_match_other_id", "detail_match", ["other_id"])


def downgrade() -> None:
    op.drop_index("ix_detail_match_other_id", table_name="detail_match")
    op.drop_table("detail_match")
