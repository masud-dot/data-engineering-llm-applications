"""Cleaning: properties that must hold for any text, and copies."""

from __future__ import annotations

import random
import re
import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st

from llmdata.clean import clean_text, language, scope
from llmdata.clean.dedup import signature, similarity
from llmdata.synthetic import WELSH_BODY, refile, truth, wording

RULES = [r"^Quillmere Mutual · page \d+ of \d+$"]


# region: property-tests
@pytest.mark.chapter(6)
@given(st.text())
def test_cleaning_twice_changes_nothing(text: str) -> None:
    once = clean_text(text, RULES)
    assert clean_text(once, RULES) == once


@pytest.mark.chapter(6)
@given(st.text())
def test_cleaned_text_is_tidy(text: str) -> None:
    out = clean_text(text, RULES)
    assert unicodedata.is_normalized("NFKC", out)
    assert "\n\n\n" not in out
    for line in out.split("\n"):
        assert line == " ".join(line.split())
        assert all(unicodedata.category(c)[0] != "C" for c in line)
        assert not re.match(RULES[0], line, re.IGNORECASE)


@pytest.mark.chapter(6)
@given(st.text(), st.text())
def test_similarity_is_symmetric(a: str, b: str) -> None:
    sig_a, sig_b = signature(a), signature(b)
    assert similarity(sig_a, sig_a) == 1.0
    assert similarity(sig_a, sig_b) == similarity(sig_b, sig_a)


# endregion


@pytest.mark.chapter(6)
def test_refiled_wording_is_a_near_duplicate() -> None:
    rng = random.Random(6)
    first, other = wording(rng, 1), wording(rng, 2)
    sig = signature("\n".join(truth(first)))
    copy = signature("\n".join(truth(refile(first, 5))))
    assert similarity(sig, copy) >= 0.8
    assert similarity(sig, signature("\n".join(truth(other)))) < 0.2


@pytest.mark.chapter(6)
def test_language_tells_english_from_welsh() -> None:
    assert (
        language("Escape of water is covered up to the limit.")
        == "en"
    )
    assert language(WELSH_BODY) == "cy"


@pytest.mark.chapter(6)
def test_two_editions_are_never_compared() -> None:
    meta = {"region": "south", "roles": ["agent"]}
    first = scope("wordings", {**meta, "edition": "2027.1"})
    assert first != scope("wordings", {**meta, "edition": "2027.2"})
