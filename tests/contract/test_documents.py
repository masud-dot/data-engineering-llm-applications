"""Document and chunk contracts."""

from typing import Any

import pytest
from pydantic import ValidationError

from llmdata.contracts import DIMENSIONS, Chunk, Document

DOC_ID, VERSION = "a" * 16, "b" * 16
ACCESS = {"region": "east", "roles": ["underwriter"]}
CHUNK: dict[str, Any] = {
    "chunk_id": f"{DOC_ID}:{VERSION}:0003",
    "doc_key": "file:wordings/east/WRD-0042.pdf",
    "ordinal": 3,
    "text": "Escape of water is covered.",
    "access": ACCESS,
}


@pytest.mark.chapter(2)
def test_chunks_validate_before_and_after_embedding() -> None:
    assert Chunk.model_validate(CHUNK).embedding is None
    full = CHUNK | {
        "embedding": [0.0] * DIMENSIONS,
        "embedding_model": "fake-hash-384",
    }
    assert Chunk.model_validate(full).embedding_model


@pytest.mark.chapter(2)
@pytest.mark.parametrize(
    "change",
    [
        {"ordinal": 4},
        {"embedding": [0.0] * 3, "embedding_model": "m"},
        {"embedding": [0.0] * DIMENSIONS},
        {"access": {"region": "east", "roles": []}},
        {"text": ""},
        {"text": "x" * 2001},
        {"doc_key": "wordings/east/WRD-0042.pdf"},
    ],
)
def test_broken_chunks_fail(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Chunk.model_validate(CHUNK | change)


@pytest.mark.chapter(2)
def test_documents_need_hex_ids_and_access() -> None:
    doc = {
        "doc_key": "claim:CLM-00042",
        "doc_id": DOC_ID,
        "version": VERSION,
        "origin": "claims",
        "access": {"region": "north", "roles": ["claims"]},
        "run_id": "r1",
    }
    assert Document.model_validate(doc).access.region == "north"
    with pytest.raises(ValidationError):
        Document.model_validate(doc | {"version": "v2"})
