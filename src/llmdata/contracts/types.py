"""Shared vocabulary for every contract."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# region: contract-types
Region = Literal["north", "south", "east", "west"]
Role = Literal["agent", "underwriter", "claims"]
Origin = Literal[
    "wordings", "endorsements", "guidelines", "emails", "claims"
]
Kind = Literal["pdf", "html", "eml", "record"]
Op = Literal["upsert", "delete"]
DocKey = Annotated[str, Field(pattern=r"^(file|claim):\S+$")]
Hex16 = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]


class Access(BaseModel):
    """Who may read a document and every chunk cut from it."""

    model_config = ConfigDict(frozen=True)

    region: Region
    roles: frozenset[Role] = Field(min_length=1)


# endregion
