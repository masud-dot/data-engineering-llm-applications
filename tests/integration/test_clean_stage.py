"""The clean stage marks copies; the view hides them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llmdata import clean, ingest, parse
from llmdata.config import Settings
from llmdata.db import connect
from llmdata.pipeline.context import Context
from llmdata.pipeline.spec import load

FIRST = "file:wordings/south/WRD-0001.pdf"
COPY = "file:wordings/south/WRD-0003.pdf"
WELSH = "file:emails/north/EM-0004.eml"
HIDDEN = (
    "SELECT doc_key FROM chunks"
    " EXCEPT SELECT doc_key FROM search_chunks"
)


def cleaned(cfg: Settings) -> dict[str, Any]:
    """Ingest, parse and clean the small corpus as run c1, twice."""
    stages = {
        s.name: s
        for s in load(Path("pipelines"), "documents", "ch06")
    }
    for module, name in (
        (ingest, "10-ingest"),
        (parse, "20-parse"),
        (clean, "30-clean"),
        (clean, "30-clean"),
    ):
        ctx = Context(
            "c1", "documents", name, cfg, stages[name].params
        )
        module.run(ctx)
    with connect(cfg.dsn) as conn:
        rows = conn.execute(
            "SELECT doc_key, left(content_hash, 16), meta FROM staged"
            " WHERE run_id = 'c1'"
        )
        return {str(k): (v, m) for k, v, m in rows}


@pytest.mark.chapter(6)
def test_clean_marks_copies_and_languages(
    landed: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    docs = cleaned(landed)
    copy_of = docs[COPY][1]["duplicate_of"]
    assert copy_of == {"doc_key": FIRST, "version": docs[FIRST][0]}
    assert docs[WELSH][1]["language"] == "cy"
    assert sum("duplicate_of" in m for _, m in docs.values()) == 1
    last = capsys.readouterr().out.splitlines()[-1]
    assert last == "near-duplicates marked: 1"


@pytest.mark.chapter(6)
def test_view_hides_copies_while_the_first_stands(
    landed: Settings,
) -> None:
    cleaned(landed)
    with connect(landed.dsn) as conn:
        conn.execute(
            "INSERT INTO documents (doc_key, doc_id, version, origin,"
            " meta, run_id) SELECT doc_key, doc_key,"
            " left(content_hash, 16), origin, meta, run_id"
            " FROM staged WHERE run_id = 'c1'"
        )
        conn.execute(
            "INSERT INTO chunks (chunk_id, doc_key, ordinal, text,"
            " embedding, embedding_model, meta, run_id)"
            " SELECT doc_key || ':0', doc_key, 0, cleaned,"
            " array_fill(0, ARRAY[384])::vector, 'none',"
            " meta - 'minhash', run_id FROM staged"
            " WHERE run_id = 'c1'"
        )
        assert conn.execute(HIDDEN).fetchall() == [(COPY,)]
        conn.execute(
            "UPDATE documents SET version = 'edited'"
            " WHERE doc_key = %s",
            (FIRST,),
        )
        assert conn.execute(HIDDEN).fetchall() == []
