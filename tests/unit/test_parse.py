"""Golden-file tests: parsed text against the generator's truth."""

from __future__ import annotations

import random
import shutil
from pathlib import Path

import pytest
from rapidfuzz.distance import Levenshtein

from llmdata.parse import PlumberParser, pdf_text
from llmdata.synthetic import (
    draw_pdf,
    endorsement,
    scan_pdf,
    truth,
    wording,
)

NO_OCR = shutil.which("tesseract") is None


# region: golden-test
def match(got: str, want: str) -> float:
    """1 minus the edit distance, ignoring runs of white space."""
    got, want = " ".join(got.split()), " ".join(want.split())
    return 1 - Levenshtein.distance(got, want) / len(want)


@pytest.mark.chapter(5)
def test_wording_matches_golden(tmp_path: Path) -> None:
    doc = wording(random.Random(5), 2)
    path = tmp_path / "wording.pdf"
    draw_pdf(path, doc["pages"], doc["table"])
    pages = PlumberParser().pages(path)
    for got, want in zip(pages, truth(doc), strict=True):
        assert match(got, want) >= 0.98
    assert "| Cover | Limit | Excess | Exclusion |" in pages[0]


@pytest.mark.chapter(5)
@pytest.mark.skipif(NO_OCR, reason="Tesseract is not installed")
def test_scan_is_read_by_ocr(tmp_path: Path) -> None:
    doc = endorsement(random.Random(5), 2)
    path = tmp_path / "endorsement.pdf"
    scan_pdf(path, doc["pages"], seed=7)
    text, scanned = pdf_text(path, PlumberParser())
    assert scanned == 2
    assert match(text, "\n\n".join(truth(doc))) >= 0.90


# endregion
