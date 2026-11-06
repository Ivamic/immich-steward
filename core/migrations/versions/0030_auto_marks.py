# SPDX-License-Identifier: AGPL-3.0-or-later
"""Marks "no sign of a place" set by the app, and photos the user said do show the place.

A mark is set by the user, or by the app when a photo is close to several photos the user marked
(D-200). A photo whose mark the user took back is not marked automatically again.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "view_photo_trash",
        sa.Column("source", sa.String(length=8), nullable=False, server_default="user"),
    )
    op.create_table(
        "view_photo_keep",
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("asset.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_view_photo_keep_account_id", "view_photo_keep", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_view_photo_keep_account_id", table_name="view_photo_keep")
    op.drop_table("view_photo_keep")
    # Automatic marks would read as the user's own: they go, as when the user takes one back,
    # and the next rebuild finds the photos their groups.
    op.execute(
        """
        DELETE FROM view_group_member AS member
        USING view_photo_trash AS mark, view_group
        WHERE mark.asset_id = member.asset_id AND mark.source <> 'user'
            AND member.role = 'excluded' AND view_group.id = member.group_id
            AND NOT view_group.dissolved
        """
    )
    op.execute("DELETE FROM view_photo_trash WHERE source <> 'user'")
    op.drop_column("view_photo_trash", "source")
