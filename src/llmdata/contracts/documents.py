"""Contracts for documents and chunks."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from llmdata.contracts.types import Access, DocKey, Hex16, Origin

MAX_CHUNK_CHARS = 2000
DIMENSIONS = 384


# region: document-chunk
class Document(BaseModel):
    """One version of one source document, as the index holds it."""

    model_config = ConfigDict(frozen=True)

    doc_key: DocKey
    doc_id: Hex16
    version: Hex16
    origin: Origin
    access: Access
    run_id: str = Field(min_length=1)


class Chunk(BaseModel):
    """A piece of one document version, ready to index."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(
        pattern=r"^[0-9a-f]{16}:[0-9a-f]{16}:\d{4}$"
    )
    doc_key: DocKey
    ordinal: int = Field(ge=0, le=9999)
    text: str = Field(min_length=1, max_length=MAX_CHUNK_CHARS)
    embedding: list[float] | None = None
    embedding_model: str | None = None
    access: Access

    @model_validator(mode="after")
    def consistent(self) -> Chunk:
        if not self.chunk_id.endswith(f":{self.ordinal:04d}"):
            raise ValueError("chunk_id does not end with the ordinal")
        if (self.embedding is None) != (self.embedding_model is None):
            raise ValueError("embedding and its model go together")
        if self.embedding and len(self.embedding) != DIMENSIONS:
            raise ValueError(f"embedding needs {DIMENSIONS} values")
        return self


# endregion
