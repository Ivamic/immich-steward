# SPDX-License-Identifier: AGPL-3.0-or-later
"""How close the photos of a group are to each other, for the list of groups.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("view_group", sa.Column("similarity", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("view_group", "similarity")
