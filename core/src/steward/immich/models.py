# SPDX-License-Identifier: AGPL-3.0-or-later
"""Response models for the subset of the Immich API we use. Unknown fields are ignored."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ImmichModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class ServerVersion(ImmichModel):
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class ApiKeyInfo(ImmichModel):
    id: UUID
    name: str
    permissions: list[str]


class ImmichUser(ImmichModel):
    id: UUID
    name: str
    email: str
    is_admin: bool = False
