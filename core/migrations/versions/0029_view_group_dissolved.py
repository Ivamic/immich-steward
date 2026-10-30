# SPDX-License-Identifier: AGPL-3.0-or-later
"""Groups the user dissolved: kept, so that the rule does not build them again.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "view_group",
        sa.Column("dissolved", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("view_group", "dissolved")
