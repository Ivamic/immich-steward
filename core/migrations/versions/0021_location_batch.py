# SPDX-License-Identifier: AGPL-3.0-or-later
"""Locations written to several photos at once share a batch, so that they are undone together.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("location_change", sa.Column("batch_id", sa.Uuid()))
    op.create_index("ix_location_change_batch_id", "location_change", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_location_change_batch_id", table_name="location_change")
    op.drop_column("location_change", "batch_id")
