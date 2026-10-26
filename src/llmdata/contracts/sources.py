"""Contracts for what source systems send and ingestion stages."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from llmdata.contracts.types import DocKey, Kind, Op, Origin, Region


# region: claim-record
class ClaimRecord(BaseModel):
    """One row of the claims system's claims table."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    claim_id: str = Field(pattern=r"^CLM-\d{5}$")
    policy_id: str = Field(pattern=r"^POL-\d{5}$")
    region: Region
    status: Literal["open", "assessing", "settled", "closed"]
    note: str = Field(min_length=20)
    updated_at: AwareDatetime
    deleted_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def delete_moves_watermark(self) -> ClaimRecord:
        if self.deleted_at and self.deleted_at > self.updated_at:
            raise ValueError(
                "deleted_at is after updated_at: a watermark"
                " would never see this delete"
            )
        return self


# endregion


class SourceItem(BaseModel):
    """One change to one source document, as ingestion stages it."""

    model_config = ConfigDict(frozen=True)

    doc_key: DocKey
    op: Op
    origin: Origin
    kind: Kind
    content_hash: str = ""
    ref: str = ""
    raw: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
