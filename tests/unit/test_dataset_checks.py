"""Splits, teacher and checks for the summarisation dataset."""

from __future__ import annotations

from collections import Counter

import pytest

from llmdata.training import ngrams, problem, split_of
from llmdata.training.teacher import FakeTeacher

NOTE = (
    "Caller [NAME] ([PHONE], [EMAIL]) reported storm damage to the"
    " garden fence. Storm cover applies; fence repair quoted."
)


@pytest.mark.chapter(17)
def test_splits_follow_the_claim_in_fixed_shares() -> None:
    keys = [f"claim:CLM-{i:05d}" for i in range(1, 2001)]
    shares = Counter(split_of(k) for k in keys)
    assert split_of("claim:CLM-00009") == "test"
    assert (
        150 < shares["test"] < 250
        and 150 < shares["validation"] < 250
    )


@pytest.mark.chapter(17)
def test_the_teacher_only_uses_the_notes_words() -> None:
    summary = FakeTeacher().summarise(NOTE)
    assert summary.startswith("Reported storm damage to.")
    assert problem(NOTE, summary) is None


@pytest.mark.chapter(17)
def test_checks_reject_invented_words_and_personal_data() -> None:
    assert problem(NOTE, "Reported flood damage.") == (
        "summary says what the note does not"
    )
    leaked = NOTE.replace("[PHONE]", "07700 900123")
    assert (
        problem(leaked, "Reported storm damage.") == "personal data"
    )


@pytest.mark.chapter(17)
def test_overlap_counts_words_in_a_row() -> None:
    a = ngrams("one two three four", 3)
    assert a == {("one", "two", "three"), ("two", "three", "four")}
    assert not a & ngrams("four three two one", 3)
