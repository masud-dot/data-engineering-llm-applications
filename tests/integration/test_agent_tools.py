"""The triage agent's data: its contract, its reach, its age."""

from __future__ import annotations

import pytest

from llmdata.agents import (
    ClaimStatus,
    StaleData,
    as_reader,
    claim_status,
)
from llmdata.config import Settings
from llmdata.db import connect
from llmdata.pipeline.__main__ import main as pipeline

COLUMNS = (
    "SELECT column_name FROM information_schema.columns"
    " WHERE (table_schema, table_name) = ('agent', 'claims')"
    " ORDER BY ordinal_position"
)
SETTLE = (
    "UPDATE claims SET status = 'settled',"
    " updated_at = '2027-02-01 09:00Z' WHERE claim_id = 'CLM-00008'"
)
AGE = (
    "UPDATE agent.claim_facts"
    " SET read_at = read_at - interval '1 day'"
)


def status(dsn: str, claim_id: str) -> ClaimStatus | None:
    with connect(dsn) as conn:
        as_reader(conn, "north", "claims")  # 4 and 8 are North
        return claim_status(conn, claim_id)


# region: agent-tests
@pytest.mark.chapter(18)
def test_the_view_keeps_the_tool_contract(synced: Settings) -> None:
    with connect(synced.dsn) as conn:
        names = [n for (n,) in conn.execute(COLUMNS)]
    assert names == [*ClaimStatus.model_fields, "age"]


@pytest.mark.chapter(18)
def test_the_agent_reads_only_its_region(synced: Settings) -> None:
    assert status(synced.dsn, "CLM-00004") is not None
    assert status(synced.dsn, "CLM-00001") is None  # South
    with connect(synced.dsn) as conn:
        as_reader(conn, "north", "underwriter")
        assert (
            conn.execute("SELECT * FROM agent.claims").fetchall()
            == []
        )


@pytest.mark.chapter(18)
def test_a_status_is_current_or_refused(synced: Settings) -> None:
    with connect(synced.source_dsn, vectors=False) as source:
        source.execute(SETTLE)
    before = status(synced.dsn, "CLM-00008")
    assert before is not None and before.status != "settled"
    with connect(synced.dsn) as conn:
        conn.execute(AGE)  # as if the syncs had failed for a day
    with pytest.raises(StaleData):
        status(synced.dsn, "CLM-00008")
    assert pipeline(["run", "claim_facts", "--run-id", "f1"]) == 0
    after = status(synced.dsn, "CLM-00008")
    assert after is not None and after.status == "settled"
    assert not after.is_open and after.as_of > before.as_of


# endregion
