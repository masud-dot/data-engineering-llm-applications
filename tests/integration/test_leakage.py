"""Fine-tuning data: stable splits, clean files, no test text."""

from __future__ import annotations

import json
from typing import Any

import pytest

from llmdata.config import Settings
from llmdata.db import connect
from llmdata.pipeline.__main__ import main as pipeline
from llmdata.training import ngrams


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
    with connect(landed.dsn) as conn:  # a reset keeps datasets
        conn.execute("TRUNCATE training.sets, evals.examples CASCADE")
    assert run("documents", "r0") == 0
    return landed


SPLITS = (
    "SELECT doc_key, doc_version, split FROM training.examples"
    " UNION SELECT doc_key, doc_version, 'test' FROM evals.examples"
)
REASON = (
    "SELECT rejected FROM training.examples"
    " WHERE doc_key = 'claim:CLM-00001'"
)
COPY = (
    "UPDATE claims SET note = (SELECT note FROM claims"
    " WHERE claim_id = 'CLM-00009') || ' Copied for review.',"
    " updated_at = '2027-02-01 09:00Z' WHERE claim_id = 'CLM-00001'"
)


# region: leakage-tests
@pytest.mark.chapter(17)
def test_each_claim_stays_in_one_split(indexed: Settings) -> None:
    assert run("summaries", "t1") == 0
    with connect(indexed.source_dsn, vectors=False) as conn:
        conn.execute(
            "UPDATE claims SET note = note || ' Revised.',"
            " updated_at = '2027-02-01 09:00Z'"
        )
    assert run("documents", "r1") == 0
    assert run("summaries", "t2") == 0  # every claim, new versions
    rows = query(indexed.dsn, SPLITS)  # two versions of each claim
    assert len(rows) == 20
    assert len({(key, split) for key, _, split in rows}) == 10


@pytest.mark.chapter(17)
def test_a_copied_test_note_never_reaches_training(
    indexed: Settings,
) -> None:
    with connect(indexed.source_dsn, vectors=False) as conn:
        conn.execute(COPY)  # CLM-00009 is a test claim
    assert run("documents", "r1") == 0
    assert run("summaries", "t1") == 0
    [(why,)] = query(indexed.dsn, REASON)
    assert why == "overlaps evaluation data"
    [(test,)] = query(
        indexed.dsn, "SELECT prompt FROM evals.examples"
    )
    out = indexed.data_dir / "datasets/summaries/v1"
    train = (out / "train.jsonl").read_text()
    assert not ngrams(train, 8) & ngrams(test, 8)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["rejected"] == {"overlaps evaluation data": 1}


# endregion
