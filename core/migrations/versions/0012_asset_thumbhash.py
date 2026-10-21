# SPDX-License-Identifier: AGPL-3.0-or-later
"""Immich's hash of the thumbnails of an asset, to notice a rotated or edited photo.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("asset", sa.Column("thumbhash", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("asset", "thumbhash")
