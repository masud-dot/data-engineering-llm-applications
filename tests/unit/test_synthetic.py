import pytest

from llmdata.synthetic import (
    corpus_hash,
    parse_changes,
    plan,
    recorded,
)


@pytest.mark.chapter(3)
def test_corpus_plans_match_their_recorded_hashes() -> None:
    for scale in ("small", "full"):
        assert corpus_hash(plan(scale)) == recorded(scale)


@pytest.mark.chapter(11)
def test_change_spec_parses() -> None:
    assert parse_changes("update:5,soft:2,hard:1") == {
        "update": 5.0,
        "soft": 2.0,
        "hard": 1.0,
    }
