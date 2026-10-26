"""Replay tests: ingesting the same input twice changes nothing."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from llmdata import ingest
from llmdata.config import Settings
from llmdata.db import connect, reset
from llmdata.pipeline.context import Context
from llmdata.synthetic import load_claims, plan, write_files


@pytest.fixture
def landed(pg: Settings, tmp_path: Path) -> Settings:
    """The small day-0 corpus in a fresh landing zone; empty index."""
    reset(pg.dsn)
    corpus = plan("small")
    write_files(corpus, tmp_path)
    load_claims(pg.source_dsn, corpus["claims"])
    return replace(pg, data_dir=tmp_path)


# region: replay-test
def ingest_run(cfg: Settings, run_id: str) -> list[tuple[str, str]]:
    ingest.run(Context(run_id, "documents", "10-ingest", cfg))
    with connect(cfg.dsn) as conn:
        rows = conn.execute(
            "SELECT doc_key, content_hash FROM staged"
            " WHERE run_id = %s ORDER BY doc_key",
            (run_id,),
        )
        return [(str(key), str(digest)) for key, digest in rows]


def publish(cfg: Settings, run_id: str) -> None:
    """Record staged versions as indexed, as Chapter 10 will."""
    with connect(cfg.dsn) as conn:
        conn.execute(
            "INSERT INTO documents (doc_key, doc_id, version,"
            " origin, run_id) SELECT doc_key, doc_key,"
            " left(content_hash, 16), origin, run_id"
            " FROM staged WHERE run_id = %s",
            (run_id,),
        )


@pytest.mark.chapter(4)
def test_replay_stages_same_rows(landed: Settings) -> None:
    first = ingest_run(landed, "r1")
    assert len(first) == 21  # 11 landed files and 10 claims
    assert ingest_run(landed, "r1") == first


@pytest.mark.chapter(4)
def test_published_docs_not_restaged(landed: Settings) -> None:
    ingest_run(landed, "r1")
    publish(landed, "r1")
    assert ingest_run(landed, "r2") == []


# endregion


@pytest.mark.chapter(4)
def test_changed_file_is_staged_alone(landed: Settings) -> None:
    ingest_run(landed, "r1")
    publish(landed, "r1")
    landing = landed.data_dir / "landing"
    path = sorted(landing.glob("guidelines/*/*.html"))[0]
    path.write_text(path.read_text() + "<p>Revised.</p>\n")
    key = f"file:{path.relative_to(landing).as_posix()}"
    assert [k for k, _ in ingest_run(landed, "r2")] == [key]


@pytest.mark.chapter(4)
def test_files_still_landing_are_skipped(landed: Settings) -> None:
    first = ingest_run(landed, "r1")
    folder = sorted((landed.data_dir / "landing").glob("emails/*"))[0]
    (folder / ".EM-9999.eml.part").write_text("half a message")
    assert ingest_run(landed, "r2") == first


@pytest.mark.chapter(4)
def test_manifest_records_every_file(landed: Settings) -> None:
    ingest_run(landed, "r1")
    with connect(landed.dsn) as conn:
        row = conn.execute(
            "SELECT manifest FROM pending_checkpoints"
            " WHERE run_id = 'r1' AND source = 'files'"
        ).fetchone()
    assert row is not None
    assert len(row[0]) == 11
    assert all(len(digest) == 64 for digest in row[0].values())
