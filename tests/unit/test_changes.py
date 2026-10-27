"""Change events, the removal guard and SLA durations."""

from __future__ import annotations

import json

import pytest

from llmdata.freshness import seconds
from llmdata.freshness.cdc import from_event
from llmdata.freshness.sources import SourceGone, guard

ROW = {
    "claim_id": "CLM-00007",
    "policy_id": "POL-00042",
    "region": "north",
    "status": "assessing",
    "note": "Escape of water from a burst pipe in the loft.",
    "updated_at": "2027-01-05T09:00:00.000000Z",
    "deleted_at": None,
}


def event(op: str, before: object, after: object) -> bytes:
    source = {"connector": "postgresql", "table": "claims"}
    return json.dumps(
        {"before": before, "after": after, "source": source, "op": op}
    ).encode()


@pytest.mark.chapter(11)
@pytest.mark.parametrize("op", ["r", "c", "u"])
def test_snapshot_insert_and_update_events_upsert(op: str) -> None:
    item = from_event(event(op, None, ROW))
    assert item and (item.doc_key, item.op) == (
        "claim:CLM-00007",
        "upsert",
    )


@pytest.mark.chapter(11)
def test_soft_and_hard_deletes_become_deletes() -> None:
    soft = ROW | {"deleted_at": "2027-01-05T09:00:00Z"}
    hard = {"claim_id": "CLM-00007"} | {
        k: None for k in ROW if k != "claim_id"
    }
    for value in (event("u", ROW, soft), event("d", hard, None)):
        item = from_event(value)
        assert item and item.op == "delete"
    assert from_event(None) is None  # Kafka's tombstone


@pytest.mark.chapter(11)
def test_guard_allows_a_little_and_refuses_a_lot() -> None:
    guard("landing zone", 100, 20, 0.2)
    guard("landing zone", 0, 0, 0.2)
    with pytest.raises(SourceGone):
        guard("landing zone", 100, 21, 0.2)


@pytest.mark.chapter(11)
def test_sla_durations() -> None:
    assert [seconds(d) for d in ("PT1H", "PT4H", "P1D", "P3D")] == [
        3600,
        14400,
        86400,
        259200,
    ]
