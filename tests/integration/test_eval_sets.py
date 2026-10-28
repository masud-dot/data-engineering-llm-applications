"""Evaluation sets: kept versions, stale labels, leaks and scores."""

from __future__ import annotations

from typing import Any

import pytest

from llmdata.config import Settings
from llmdata.datasets import LeakError, StaleError
from llmdata.db import connect
from llmdata.pipeline.__main__ import main as pipeline


def run(name: str, run_id: str) -> int:
    return pipeline(["run", name, "--run-id", run_id])


def query(dsn: str, sql: str) -> list[Any]:
    with connect(dsn) as conn:
        return conn.execute(sql).fetchall()


@pytest.fixture
def indexed(
    landed: Settings, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    monkeypatch.setenv("LLMDATA_DATA_DIR", str(landed.data_dir))
    with connect(landed.dsn) as conn:  # a reset keeps evaluation sets
        conn.execute("TRUNCATE evals.sets CASCADE")
    assert run("documents", "r0") == 0
    return landed


ITEMS = "SELECT question, evidence FROM evals.items"
SCORES = "SELECT version, stale FROM evals.scores ORDER BY scored_at"


@pytest.mark.chapter(16)
def test_a_version_is_kept_and_scored_each_run(
    indexed: Settings,
) -> None:
    assert run("eval_sets", "e1") == 0
    assert run("eval_sets", "e2") == 0
    assert query(indexed.dsn, SCORES) == [(1, 0), (1, 0)]


# region: eval-tests
@pytest.mark.chapter(16)
def test_questions_in_the_index_stop_scoring(
    indexed: Settings,
) -> None:
    assert run("eval_sets", "e1") == 0
    page = "".join(
        f"<p>{q} {e}</p>" for q, e in query(indexed.dsn, ITEMS)
    )
    faq = indexed.data_dir / "landing/guidelines/north/FAQ.html"
    faq.write_text(f"<h1>Schedule questions</h1>{page}")
    assert run("documents", "r1") == 0
    with pytest.raises(LeakError):
        run("eval_sets", "e2")


@pytest.mark.chapter(16)
def test_a_revised_wording_needs_a_new_version(
    indexed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run("eval_sets", "e1") == 0
    [(key,)] = query(
        indexed.dsn, "SELECT min(doc_key) FROM evals.items"
    )
    path = indexed.data_dir / "landing" / key.split(":", 1)[1]
    path.write_bytes(path.read_bytes() + b"\n% revised\n")
    assert run("documents", "r1") == 0
    with pytest.raises(StaleError):  # 5 of 10 items label old text
        run("eval_sets", "e2")
    monkeypatch.setenv("LLMDATA_CONF", '{"rebuild": true}')
    assert run("eval_sets", "e3") == 0
    assert query(indexed.dsn, SCORES) == [(1, 0), (2, 0)]


# endregion
