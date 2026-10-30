# SPDX-License-Identifier: AGPL-3.0-or-later
"""Groups of photos of one view: the neighbors of every photo, the groups and their photos.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIM = 8448


def upgrade() -> None:
    # The neighbors among all the photos, with a location or not (`ix_embedding_search` has only
    # those with one).
    op.execute(
        f"CREATE INDEX ix_embedding_all ON embedding USING hnsw "
        f"((binary_quantize(vector)::bit({DIM})) bit_hamming_ops) WHERE NOT region"
    )
    op.create_table(
        "view_neighbor",
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("neighbor_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("similarities", postgresql.ARRAY(postgresql.REAL()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_view_neighbor_account_id", "view_neighbor", ["account_id"])
    op.create_table(
        "view_group",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("trash", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_view_group_account_id", "view_group", ["account_id"])
    op.create_table(
        "view_group_member",
        sa.Column(
            "group_id",
            sa.Uuid(),
            sa.ForeignKey("view_group.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_view_group_member_account_id", "view_group_member", ["account_id"])
    op.create_index(
        "ux_view_group_member_asset",
        "view_group_member",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("role <> 'excluded'"),
    )


def downgrade() -> None:
    op.drop_table("view_group_member")
    op.drop_table("view_group")
    op.drop_table("view_neighbor")
    op.execute("DROP INDEX ix_embedding_all")
