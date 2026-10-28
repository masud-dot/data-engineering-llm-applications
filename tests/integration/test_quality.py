"""The quality gate: a halving parser, a regional shift, the index."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from llmdata.config import Settings
from llmdata.db import connect
from llmdata.index import index_hash
from llmdata.parse import PlumberParser
from llmdata.pipeline.__main__ import main as pipeline
from llmdata.quality import QualityError, index_check


def run(run_id: str) -> int:
    return pipeline(
        ["run", "documents", "--until", "ch13", "--run-id", run_id]
    )


def query(dsn: str, sql: str, *args: Any) -> list[Any]:
    with connect(dsn) as conn:
        return [row[0] for row in conn.execute(sql, args)]


FAILED = (
    "SELECT name || ' ' || scope FROM quality_results"
    " WHERE run_id = %s AND NOT passed ORDER BY 1"
)


@pytest.fixture
def day0(
    landed: Settings, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    monkeypatch.setenv("LLMDATA_DATA_DIR", str(landed.data_dir))
    assert run("r0") == 0
    return landed


# region: quality-tests
@pytest.mark.chapter(13)
def test_parser_that_halves_text_publishes_nothing(
    day0: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    with connect(day0.dsn) as conn:
        before = index_hash(conn)
    pages = PlumberParser.pages

    def halved(self: PlumberParser, path: Path) -> list[str]:
        return [text[: len(text) // 2] for text in pages(self, path)]

    monkeypatch.setattr(PlumberParser, "pages", halved)
    query(day0.dsn, "UPDATE ledger SET code = 'old' RETURNING 1")
    backfill = {"backfill": {"origin": "wordings"}}
    monkeypatch.setenv("LLMDATA_CONF", json.dumps(backfill))
    with pytest.raises(QualityError):
        run("b1")
    with connect(day0.dsn) as conn:
        assert index_hash(conn) == before
    assert query(day0.dsn, FAILED, "b1") == [
        "documents that lost text "
    ]


# endregion


@pytest.mark.chapter(13)
def test_regional_shift_is_drift(
    day0: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pipes = tmp_path / "pipelines"  # judge drift from 5 documents
    shutil.copytree("pipelines", pipes)
    gate = pipes / "documents" / "85-quality-gate.toml"
    gate.write_text(gate.read_text().replace("= 20 ", "= 5 "))
    monkeypatch.setenv("LLMDATA_PIPELINES_DIR", str(pipes))
    with connect(day0.source_dsn, vectors=False) as src:
        src.execute(
            "UPDATE claims SET region = 'south', note = note"
            " || ' Refiled.', updated_at = '2027-02-01 09:00Z'"
            " WHERE claim_id <= 'CLM-00008'"
        )
    with pytest.raises(QualityError):
        run("r1")
    assert query(day0.dsn, FAILED, "r1") == [
        "share of claims drift south"
    ]
    accept = {"accept": ["share of claims drift"]}
    monkeypatch.setenv("LLMDATA_CONF", json.dumps(accept))
    assert run("r1") == 0  # a person accepted the shift


@pytest.mark.chapter(13)
def test_index_finds_chunks_by_their_own_vectors(
    day0: Settings,
) -> None:
    assert index_check(size=20) == {
        "sampled": 20,
        "found": 20,
        "recall": 1.0,
    }
