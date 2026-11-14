# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Immich locked folder of an account: its Immich session and whether it is open (D-216).

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "locked_folder",
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("session_encrypted", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("active_at", sa.DateTime(timezone=True)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("failed_pins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_until", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    # Older versions know neither locked photos nor "missing" ones (taken for the timeline, they
    # would show broken); the next sync brings back those still in the timeline.
    op.execute("DELETE FROM asset WHERE visibility IN ('locked', 'missing')")
    op.drop_table("locked_folder")
