"""The small corpus through every stage, against a golden index."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llmdata.config import Settings
from llmdata.db import connect
from llmdata.pipeline.__main__ import main as pipeline

GOLDEN = Path("tests/golden/small-index.json")

# region: golden-index
SUMMARY = (
    "SELECT d.doc_key, d.version, d.meta ->> 'region',"
    " count(*), string_agg(c.section, ' | ' ORDER BY c.ordinal),"
    " left(md5(string_agg(c.text || c.embedding::text, ''"
    " ORDER BY c.ordinal)), 12)"
    " FROM documents d JOIN chunks c USING (doc_key)"
    " GROUP BY d.doc_key ORDER BY d.doc_key"
)
FIELDS = ("version", "region", "chunks", "sections", "content")


@pytest.mark.chapter(14)
def test_small_corpus_matches_the_golden_index(
    landed: Settings,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    monkeypatch.setenv("LLMDATA_DATA_DIR", str(landed.data_dir))
    assert pipeline(["run", "documents", "--run-id", "golden"]) == 0
    with connect(landed.dsn) as conn:
        got = {
            key: dict(zip(FIELDS, rest, strict=True))
            for key, *rest in conn.execute(SUMMARY)
        }
    if request.config.getoption("--update-golden"):
        GOLDEN.write_text(json.dumps(got, indent=1) + "\n")
    assert got == json.loads(GOLDEN.read_text())


# endregion
