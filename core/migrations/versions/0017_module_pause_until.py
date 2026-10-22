# SPDX-License-Identifier: AGPL-3.0-or-later
"""A pause of worker modules for a while: it ends by itself.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("module_pause", sa.Column("until", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("module_pause", "until")
