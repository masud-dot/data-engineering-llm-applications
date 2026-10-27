"""Failed, resumed and abandoned runs, and backfills."""

from __future__ import annotations

import json
from typing import Any

import pytest

from llmdata.config import Settings
from llmdata.db import connect
from llmdata.freshness import compare, show
from llmdata.index import index_hash
from llmdata.pipeline.__main__ import main as pipeline
from llmdata.pipeline.context import Context
from llmdata.synthetic import apply_changes, parse_changes

CHANGES = parse_changes("update:10,soft:10,hard:10")


def run(run_id: str) -> int:
    return pipeline(
        ["run", "documents", "--until", "ch12", "--run-id", run_id]
    )


def query(dsn: str, sql: str, *args: Any) -> list[Any]:
    with connect(dsn) as conn:
        return [row[0] for row in conn.execute(sql, args)]


def state(cfg: Settings) -> tuple[str, dict[str, object]]:
    with connect(cfg.dsn) as conn:
        return index_hash(conn)[0], show()


def crash(self: Context) -> None:
    raise RuntimeError("connection lost mid-commit")


@pytest.fixture
def day1(
    landed: Settings, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    monkeypatch.setenv("LLMDATA_DATA_DIR", str(landed.data_dir))
    assert run("r0") == 0
    apply_changes(landed.source_dsn, landed.data_dir, 1, CHANGES)
    return landed


# region: recovery-tests
@pytest.mark.chapter(12)
def test_failed_run_changes_nothing_until_resumed(
    day1: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = state(day1)
    with monkeypatch.context() as m:
        m.setattr(Context, "pause_point", crash)
        with pytest.raises(RuntimeError):
            run("r1")
    assert state(day1) == before
    status = "SELECT status FROM ledger WHERE run_id = %s"
    assert query(day1.dsn, status, "r1") == ["running"]
    assert run("r1") == 0  # resume: the same run ID
    assert query(day1.dsn, status, "r1") == ["succeeded"]
    assert compare()["match"]


@pytest.mark.chapter(12)
def test_new_run_abandons_an_unfinished_one(
    day1: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as m:
        m.setattr(Context, "pause_point", crash)
        with pytest.raises(RuntimeError):
            run("r1")
    assert run("r2") == 0
    assert query(
        day1.dsn, "SELECT status FROM ledger WHERE run_id = 'r1'"
    ) == ["abandoned"]
    assert query(
        day1.dsn, "SELECT count(*) FROM staged WHERE run_id = 'r1'"
    ) == [0]
    assert compare()["match"]


# endregion


@pytest.mark.chapter(12)
def test_backfill_works_in_batches_and_changes_nothing(
    landed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLMDATA_DATA_DIR", str(landed.data_dir))
    assert run("r0") == 0
    before = state(landed)
    query(landed.dsn, "UPDATE ledger SET code = 'old' RETURNING 1")
    scope = {"origin": "claims", "batch": 4}
    monkeypatch.setenv(
        "LLMDATA_CONF", json.dumps({"backfill": scope})
    )
    done = []
    for run_id in ("b1", "b2", "b3", "b4"):
        assert run(run_id) == 0
        done += query(
            landed.dsn,
            "SELECT count(*) FROM documents WHERE run_id = %s",
            run_id,
        )
    assert done == [4, 4, 2, 0]
    assert state(landed)[0] == before[0]  # same code, same index
