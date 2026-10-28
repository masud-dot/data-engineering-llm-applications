"""Evaluation items: one question per schedule row."""

from __future__ import annotations

import pytest

from llmdata.datasets import QUESTION, ROW, digest

SCHEDULE = """\
| Cover | Limit | Excess | Exclusion |
| --- | --- | --- | --- |
| Escape of water | GBP 12000 | GBP 350 | Gradual deterioration |
| Theft | GBP 4500 | GBP 100 | Unoccupied over 60 days |
"""


@pytest.mark.chapter(16)
def test_each_schedule_row_becomes_one_question() -> None:
    rows = [m.groupdict() for m in ROW.finditer(SCHEDULE)]
    assert [r["excess"] for r in rows] == ["GBP 350", "GBP 100"]
    assert QUESTION.format(**rows[1]) == (
        "What excess applies to Theft cover with a GBP 4500 limit?"
    )


@pytest.mark.chapter(16)
def test_item_ids_do_not_depend_on_key_order() -> None:
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})
