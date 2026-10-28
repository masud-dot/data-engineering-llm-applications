"""Every wording in the golden set, parsed against its truth."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llmdata.parse import PlumberParser
from llmdata.synthetic import GOLDEN, draw_pdf, plan, truth
from tests.unit.test_parse import match

# region: golden-set
WORDINGS = plan("full")["wordings"][: GOLDEN["digital"]]


@pytest.mark.chapter(14)
@pytest.mark.parametrize("doc", WORDINGS, ids=lambda d: d["name"])
def test_golden_wording_parses(
    doc: dict[str, Any], tmp_path: Path
) -> None:
    path = tmp_path / f"{doc['name']}.pdf"
    draw_pdf(path, doc["pages"], doc["table"])
    pages = PlumberParser().pages(path)
    scores = [
        match(got, want)
        for got, want in zip(pages, truth(doc), strict=True)
    ]
    assert min(scores) >= 0.98, scores


# endregion
