"""The chunk stage on the small corpus: sizes, ordinals, sections."""

from __future__ import annotations

from pathlib import Path

import pytest

from llmdata import chunk, clean, ingest, parse
from llmdata.config import Settings
from llmdata.contracts.documents import MAX_CHUNK_CHARS
from llmdata.db import connect
from llmdata.pipeline.context import Context
from llmdata.pipeline.spec import load


@pytest.mark.chapter(7)
def test_chunk_stage_follows_structure(landed: Settings) -> None:
    stages = {s.name: s for s in load(Path("pipelines"), "documents")}
    for module, name in (
        (ingest, "10-ingest"),
        (parse, "20-parse"),
        (clean, "30-clean"),
        (chunk, "40-chunk"),
    ):
        ctx = Context(
            "k1", "documents", name, landed, stages[name].params
        )
        module.run(ctx)
    with connect(landed.dsn) as conn:
        rows = conn.execute(
            "SELECT doc_key, array_agg(ordinal ORDER BY ordinal),"
            " array_agg(section ORDER BY ordinal), max(length(text))"
            " FROM staged_chunks WHERE run_id = 'k1' GROUP BY doc_key"
        ).fetchall()
    found = {str(k): (o, s, n) for k, o, s, n in rows}
    assert len(found) == 21  # every document has chunks
    for ordinals, _, longest in found.values():
        assert ordinals == list(range(len(ordinals)))
        assert longest <= min(900, MAX_CHUNK_CHARS)
    sections = found["file:wordings/south/WRD-0001.pdf"][1]
    assert sections == [
        "1. Cover",
        "2. Conditions",
        "3. Exclusions",
        "4. Claims",
        "5. Complaints",
    ]
