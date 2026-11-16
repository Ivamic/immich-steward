# SPDX-License-Identifier: AGPL-3.0-or-later
"""Albums: the account's role, the cover and the period, for changing albums (D-233).

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Filled in by the next sync.
    op.add_column("album", sa.Column("role", sa.String(16), nullable=False, server_default="owner"))
    op.add_column("album", sa.Column("thumbnail_immich_id", sa.Uuid(), nullable=True))
    op.add_column("album", sa.Column("start_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("album", sa.Column("end_date", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("album", "end_date")
    op.drop_column("album", "start_date")
    op.drop_column("album", "thumbnail_immich_id")
    op.drop_column("album", "role")
