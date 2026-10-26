"""Day-0 load, day-1 changes, a crash mid-commit, and determinism."""

from __future__ import annotations

import pytest

from llmdata.config import Settings
from llmdata.db import connect, reset
from llmdata.freshness import compare, show
from llmdata.index import index_hash
from llmdata.pipeline.__main__ import main as pipeline
from llmdata.pipeline.context import Context
from llmdata.synthetic import (
    apply_changes,
    load_claims,
    parse_changes,
    plan,
    write_files,
)

CHANGES = parse_changes("update:10,soft:10,hard:10")


def day0(cfg: Settings) -> None:
    corpus = plan("small")
    write_files(corpus, cfg.data_dir)
    load_claims(cfg.source_dsn, corpus["claims"])


def current(cfg: Settings) -> str:
    with connect(cfg.dsn) as conn:
        return index_hash(conn)[0]


@pytest.mark.chapter(12)
def test_freshness_recovery_and_determinism(
    pg: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset(pg.dsn)
    day0(pg)
    assert pipeline(["run", "documents", "--run-id", "r0"]) == 0
    first = current(pg)
    assert compare()["match"]

    apply_changes(pg.source_dsn, pg.data_dir, 1, CHANGES)
    assert pipeline(["run", "documents", "--run-id", "r1"]) == 0
    assert compare()["match"]

    apply_changes(pg.source_dsn, pg.data_dir, 2, CHANGES)
    before, marks = current(pg), show()

    def crash(self: Context) -> None:
        raise RuntimeError("killed mid-commit")

    monkeypatch.setattr(Context, "pause_point", crash)
    with pytest.raises(RuntimeError):
        pipeline(["run", "documents", "--run-id", "r2"])
    assert current(pg) == before and show() == marks
    monkeypatch.undo()
    assert pipeline(["run", "documents", "--run-id", "r2"]) == 0
    assert compare()["match"]

    hashes = []
    for run in ("a", "b"):
        reset(pg.dsn)
        day0(pg)
        assert pipeline(["run", "documents", "--run-id", run]) == 0
        hashes.append(current(pg))
    assert hashes == [first, first]
