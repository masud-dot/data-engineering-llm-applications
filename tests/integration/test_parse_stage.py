"""The parse stage fills every staged row and resumes after a stop."""

from __future__ import annotations

import pytest

from llmdata import ingest, parse
from llmdata.config import Settings
from llmdata.db import connect
from llmdata.pipeline.context import Context


@pytest.mark.chapter(5)
def test_parse_fills_rows_and_resumes(
    landed: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    ingest.run(Context("p1", "documents", "10-ingest", landed))
    stage = Context("p1", "documents", "20-parse", landed)
    parse.run(stage)
    with connect(landed.dsn) as conn:
        short = conn.execute(
            "SELECT count(*) FROM staged WHERE run_id = 'p1'"
            " AND length(coalesce(parsed, '')) < 20"
        ).fetchone()
        conn.execute(
            "UPDATE staged SET parsed = NULL WHERE run_id = 'p1'"
            " AND origin = 'wordings'"
        )
    assert short == (0,)
    parse.run(stage)
    last = capsys.readouterr().out.splitlines()[-1]
    assert last == "parsed 3 documents; 0 pages by OCR"
