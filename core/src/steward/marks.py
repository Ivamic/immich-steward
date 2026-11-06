# SPDX-License-Identifier: AGPL-3.0-or-later
"""Photos marked as showing no sign of a place (a pet, a document; D-185, D-188, D-200): by
themselves (`ViewPhotoTrash`) or with their whole group (`ViewGroup.trash`). Apart from
`steward.view_groups`, so that the gallery can ask without importing the groups and the search.
"""

from typing import Any

from sqlalchemy import ColumnElement, exists, or_, select

from steward.models import Asset, ViewGroup, ViewGroupMember, ViewPhotoTrash


def is_marked(asset_id: Any = Asset.id) -> ColumnElement[bool]:
    """SQL: the photo is marked, by itself or with its whole group (the SQL twin of the mark
    `view_groups.of_photo` tells). A photo taken out of a marked group is not."""
    in_marked_group = (
        select(ViewGroupMember.asset_id)
        .join(ViewGroup, ViewGroup.id == ViewGroupMember.group_id)
        .where(
            ViewGroupMember.asset_id == asset_id,
            ViewGroupMember.role != "excluded",
            ViewGroup.trash.is_(True),
        )
    )
    return or_(exists().where(ViewPhotoTrash.asset_id == asset_id), exists(in_marked_group))
