import pytest

from llmdata.clean import clean_text
from llmdata.embed.fake import (
    RECORDED_SAMPLE_HASH,
    FakeEmbedder,
    sample_hash,
)
from llmdata.parse import html_text


@pytest.mark.chapter(5)
def test_html_drops_scripts_and_keeps_headings() -> None:
    text = html_text("<h1>Title</h1><script>x()</script><p>Body</p>")
    assert "x()" not in text and "Title" in text and "Body" in text


@pytest.mark.chapter(6)
def test_clean_removes_boilerplate_and_extra_space() -> None:
    raw = "Acme · Page 1 of 2\n  Cover   applies \n\n\n\nEnd"
    assert clean_text(raw, [r"^Acme · page \d+ of \d+$"]) == (
        "Cover applies\n\nEnd"
    )


@pytest.mark.chapter(9)
def test_fake_vectors_are_stable_and_normalised() -> None:
    vec = FakeEmbedder().vector("Escape of water is covered")
    assert vec.shape == (384,)
    assert abs(float((vec * vec).sum()) - 1.0) < 1e-5
    assert sample_hash() == RECORDED_SAMPLE_HASH
