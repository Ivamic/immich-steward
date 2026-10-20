# SPDX-License-Identifier: AGPL-3.0-or-later
"""Module runs on a part of the photo the user selected (FR-35).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("module_run", sa.Column("region", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("module_run", "region")
