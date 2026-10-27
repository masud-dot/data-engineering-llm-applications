"""Chunk boundaries: sizes, headings and whole table rows."""

from __future__ import annotations

import random
import re
from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from llmdata.chunk import SENTENCE, chunk
from llmdata.clean import clean_text
from llmdata.synthetic import truth, wording

HEADINGS = re.compile(r"^(\d+\. \S|#{2,3} )")
FOOTER = [r"^Quillmere Mutual · page \d+ of \d+$"]
TITLE, SIZE = "Policy wording", 300

word = st.sampled_from("cover excess flood theft limit claim".split())
phrase = st.lists(word, min_size=1, max_size=2).map(" ".join)
sentence = st.lists(word, min_size=3, max_size=10).map(
    lambda w: " ".join(w).capitalize() + "."
)
prose = st.lists(sentence, min_size=1, max_size=8).map(" ".join)
row = st.lists(phrase, min_size=3, max_size=3).map(
    lambda cells: "| " + " | ".join(cells) + " |"
)
table = st.lists(row, min_size=2, max_size=12).map(
    lambda rows: "\n".join(
        [rows[0], "| --- | --- | --- |", *rows[1:]]
    )
)
section = st.lists(st.one_of(prose, table), min_size=1, max_size=3)
document = st.lists(section, min_size=1, max_size=4).map(
    lambda parts: "\n".join(
        [TITLE]
        + [
            f"{n}. Part\n" + "\n\n".join(b)
            for n, b in enumerate(parts, 1)
        ]
    )
)


def units(text: str) -> Counter[str]:
    """Sentences and table rows, without titles, headings or rules."""
    lines, found = text.splitlines(), Counter[str]()
    for i, line in enumerate(lines):
        after = lines[i + 1] if i + 1 < len(lines) else ""
        if line.startswith("| ---") or after.startswith("| ---"):
            continue  # a rule, or the header row above one
        if line.startswith("|"):
            found[line] += 1
        elif line and line != TITLE and not HEADINGS.match(line):
            found.update(SENTENCE.split(line))
    return found


# region: boundary-tests
@pytest.mark.chapter(7)
@given(document)
def test_chunks_fit_and_lose_nothing(text: str) -> None:
    pieces = chunk(text, SIZE, HEADINGS)
    assert all(len(p.text) <= SIZE for p in pieces)
    got = sum((units(p.text) for p in pieces), Counter[str]())
    assert got == units(text)  # every sentence and row, once
    for p in pieces:
        lines = p.text.splitlines()
        for i, line in enumerate(lines[1:], 1):
            if line.startswith("|") and not lines[i - 1].startswith(
                "|"
            ):
                assert lines[i + 1].startswith(
                    "| ---"
                )  # header first


@pytest.mark.chapter(7)
def test_schedule_stays_whole_under_its_heading() -> None:
    doc = wording(random.Random(7), 2)
    text = clean_text("\n\n".join(truth(doc)), FOOTER)
    rows = [ln for ln in text.splitlines() if ln.startswith("|")]
    pieces = chunk(text, 900, HEADINGS)
    holders = [p for p in pieces if rows[0] in p.text]
    assert [p.section for p in holders] == ["1. Cover"]
    assert all(row in holders[0].text for row in rows)


# endregion
