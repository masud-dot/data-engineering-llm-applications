"""Data contracts shared by every stage."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Op = Literal["upsert", "delete"]
Kind = Literal["pdf", "html", "eml", "record"]


class SourceItem(BaseModel):
    """One change to one source document."""

    model_config = ConfigDict(frozen=True)

    doc_key: str = Field(min_length=3)
    op: Op
    origin: str
    kind: Kind
    content_hash: str = ""
    ref: str = ""
    raw: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
