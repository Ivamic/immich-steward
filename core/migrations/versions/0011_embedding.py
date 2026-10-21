# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vectors of photos for the similar-photos module (M3, MegaLoc).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import HALFVEC

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIM = 8448


def upgrade() -> None:
    op.create_table(
        "embedding",
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("module_run.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module_id", sa.String(32), nullable=False),
        sa.Column("module_version", sa.String(32), nullable=False),
        sa.Column("region", sa.Boolean(), nullable=False),
        sa.Column("located", sa.Boolean(), nullable=False),
        sa.Column("vector", HALFVEC(DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_embedding_asset_id", "embedding", ["asset_id"])
    op.create_index("ix_embedding_account_id", "embedding", ["account_id"])
    # The search: nearest by Hamming distance of the sign bits, then exact on the vectors (D-108).
    op.execute(
        f"CREATE INDEX ix_embedding_search ON embedding USING hnsw "
        f"((binary_quantize(vector)::bit({DIM})) bit_hamming_ops) WHERE located"
    )


def downgrade() -> None:
    op.drop_table("embedding")
