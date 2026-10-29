# SPDX-License-Identifier: AGPL-3.0-or-later
"""Satellite imagery sources of the map per account: keys, the own tile count, auto switching.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-24
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Every table is per account and goes with it.
def _account_id() -> sa.Column[uuid.UUID]:
    return sa.Column(
        "account_id",
        sa.Uuid(),
        sa.ForeignKey("account.id", ondelete="CASCADE"),
        primary_key=True,
    )


def upgrade() -> None:
    op.create_table(
        "map_source_setting",
        _account_id(),
        sa.Column("source_id", sa.String(32), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("api_key_encrypted", sa.Text()),
        sa.Column("usage_token_encrypted", sa.Text()),
        sa.Column("counted_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reset_day", sa.Integer()),
        sa.Column("key_problem", sa.String(16)),
        sa.Column("key_problem_at", sa.DateTime(timezone=True)),
        sa.Column("provider_usage", JSONB()),
    )
    op.create_table(
        "map_tile_usage",
        _account_id(),
        sa.Column("source_id", sa.String(32), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("tiles", sa.Integer(), nullable=False),
    )
    op.create_table(
        "map_auto",
        _account_id(),
        sa.Column("far_source", sa.String(32)),
        sa.Column("near_source", sa.String(32)),
        sa.Column("switch_zoom", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("map_auto")
    op.drop_table("map_tile_usage")
    op.drop_table("map_source_setting")
