"""Day-1 changes, the removal guard, copies and erasure."""

from __future__ import annotations

import shutil
from typing import Any

import psycopg
import pytest

from llmdata.config import Settings
from llmdata.db import connect
from llmdata.freshness import compare, erase
from llmdata.freshness.sources import SourceGone
from llmdata.index import index_hash
from llmdata.ingest.sources import sha256
from llmdata.pipeline.__main__ import main as pipeline
from llmdata.synthetic import apply_changes, parse_changes

CHANGES = parse_changes("update:10,soft:10,hard:10")


def run(run_id: str) -> int:
    return pipeline(
        ["run", "documents", "--until", "ch11", "--run-id", run_id]
    )


def query(dsn: str, sql: str, *args: Any) -> list[Any]:
    with connect(dsn) as conn:
        return [row[0] for row in conn.execute(sql, args)]


@pytest.fixture
def day0(
    landed: Settings, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    monkeypatch.setenv("LLMDATA_DATA_DIR", str(landed.data_dir))
    assert run("r0") == 0
    return landed


# region: freshness-tests
@pytest.mark.chapter(11)
def test_day1_changes_and_deletions_reach_the_index(
    day0: Settings,
) -> None:
    done = apply_changes(day0.source_dsn, day0.data_dir, 1, CHANGES)
    assert run("r1") == 0
    assert compare()["match"]
    deleted = query(day0.dsn, "SELECT count(*) FROM tombstones")
    gone = ("claims_soft", "claims_hard", "files_removed")
    assert deleted == [sum(done[k] for k in gone)]


@pytest.mark.chapter(11)
def test_empty_landing_zone_deletes_nothing(day0: Settings) -> None:
    with connect(day0.dsn) as conn:
        before = index_hash(conn)
    shutil.rmtree(day0.data_dir / "landing")
    with pytest.raises(SourceGone, match="refusing to delete"):
        run("r1")
    with connect(day0.dsn) as conn:
        assert index_hash(conn) == before


@pytest.mark.chapter(11)
def test_erased_claim_leaves_every_store(day0: Settings) -> None:
    key = "claim:CLM-00001"
    texts = query(
        day0.dsn, "SELECT text FROM chunks WHERE doc_key = %s", key
    )
    [digest] = query(
        day0.dsn,
        "SELECT content_hash FROM versions WHERE doc_key = %s",
        key,
    )
    erase(key, "ER-0001")
    for table in ("documents", "chunks", "staged", "versions"):
        assert query(
            day0.dsn,
            f"SELECT count(*) FROM {table} WHERE doc_key = %s",
            key,
        ) == [0]
    assert query(
        day0.dsn,
        "SELECT count(*) FROM embedding_cache"
        " WHERE text_hash = ANY(%s)",
        [sha256(t.encode()) for t in texts],
    ) == [0]
    assert not (
        day0.data_dir / "archive" / digest[:2] / digest
    ).exists()
    query(day0.dsn, "DELETE FROM checkpoints RETURNING 1")
    assert run("r1") == 0  # a full re-read finds the claim again
    assert query(
        day0.dsn,
        "SELECT count(*) FROM documents WHERE doc_key = %s",
        key,
    ) == [0]
    with pytest.raises(psycopg.errors.RaiseException):
        with connect(day0.dsn) as conn:
            conn.execute(
                "INSERT INTO documents (doc_key, doc_id, version,"
                " origin, run_id) VALUES"
                " (%s, 'x', 'x', 'claims', 'restore')",
                (key,),
            )


@pytest.mark.chapter(11)
def test_withdrawn_original_reveals_its_copy(day0: Settings) -> None:
    [(copy, original)] = [
        tuple(row)
        for row in query(
            day0.dsn,
            "SELECT ARRAY[doc_key, meta #>> '{duplicate_of,doc_key}']"
            " FROM documents WHERE meta ? 'duplicate_of'"
            " ORDER BY doc_key LIMIT 1",
        )
    ]
    hidden = "SELECT count(*) FROM search_chunks WHERE doc_key = %s"
    assert query(day0.dsn, hidden, copy) == [0]
    (day0.data_dir / "landing" / original.split(":", 1)[1]).unlink()
    assert run("r1") == 0
    assert query(day0.dsn, hidden, copy)[0] > 0


# endregion
