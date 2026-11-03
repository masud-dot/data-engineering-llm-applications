"""Operations checks: green on a healthy layer, named when not."""

from __future__ import annotations

from pathlib import Path

import pytest

from llmdata.config import Settings
from llmdata.db import connect
from llmdata.ops import OpsError, checks, run
from llmdata.pipeline.__main__ import main as pipeline
from llmdata.pipeline.context import Context

STUCK = (
    "INSERT INTO ledger (run_id, pipeline, started_at, status)"
    " VALUES ('stuck', 'documents', now() - interval '3 hours',"
    " 'running')"
)


@pytest.fixture
def healthy(synced: Settings) -> Settings:
    with connect(synced.dsn) as conn:  # sets from other tests
        conn.execute("TRUNCATE evals.sets CASCADE")
    assert pipeline(["run", "eval_sets", "--run-id", "e0"]) == 0
    return synced


# region: ops-tests
@pytest.mark.chapter(20)
def test_every_target_is_checked_and_has_a_runbook(
    healthy: Settings,
) -> None:
    with connect(healthy.dsn) as conn:
        found = checks(conn)
    assert found and all(c.ok for c in found), found
    for c in found:
        assert Path(f"docs/runbooks/{c.name}.md").exists()


@pytest.mark.chapter(20)
def test_a_missed_target_fails_and_names_its_runbook(
    healthy: Settings,
) -> None:
    with connect(healthy.dsn) as conn:
        conn.execute(STUCK)
        conn.execute(
            "UPDATE agent.claim_facts"
            " SET read_at = read_at - interval '1 hour'"
        )
    ctx = Context("o1", "ops", "10-checks", healthy)
    with pytest.raises(OpsError) as failed:
        run(ctx)
    assert "claim-facts.md" in str(failed.value)
    assert "run-stuck.md" in str(failed.value)


# endregion
