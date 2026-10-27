"""Embedding: the cache, one model per index, re-embedding, Spark."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from llmdata import chunk, clean, embed, identity, ingest, parse
from llmdata.config import Settings
from llmdata.db import connect
from llmdata.embed import reembed
from llmdata.embed.fake import FakeEmbedder
from llmdata.index.writers import apply_staged
from llmdata.pipeline.context import Context
from llmdata.pipeline.spec import load

GUIDE = "guidelines/south/GL-0001.html"
STAGES = (
    (ingest, "10-ingest"),
    (parse, "20-parse"),
    (clean, "30-clean"),
    (chunk, "40-chunk"),
    (identity, "50-identity"),
    (embed, "60-embed"),
)
WANT = "embedded 41 chunks with fake-hash-384@1; 40 from the cache"


def through(cfg: Settings, run_id: str, last: int = 6) -> None:
    """Run the first stages of the documents pipeline as one run."""
    stages = load(Path("pipelines"), "documents")
    params = {s.name: s.params for s in stages}
    for module, name in STAGES[:last]:
        module.run(
            Context(run_id, "documents", name, cfg, params[name])
        )


def models(cfg: Settings) -> set[str]:
    with connect(cfg.dsn) as conn:
        rows = conn.execute(
            "SELECT DISTINCT embedding_model FROM chunks"
        )
        return {str(m) for (m,) in rows}


# region: embed-tests
@pytest.mark.chapter(9)
def test_an_edit_reembeds_only_its_chunk(
    landed: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    through(landed, "e1")
    page = landed.data_dir / "landing" / GUIDE
    page.write_text(page.read_text() + "<p>Revised in March.</p>")
    through(landed, "e2")
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == WANT


@pytest.mark.chapter(9)
def test_a_new_model_means_a_reembed(
    landed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    through(landed, "e1")
    with connect(landed.dsn) as conn:
        apply_staged(conn, "e1")  # publish, as Chapter 10 will
    monkeypatch.setattr(FakeEmbedder, "revision", "2")
    with pytest.raises(RuntimeError, match="needs a re-embed"):
        through(landed, "e2")
    with connect(landed.dsn) as conn:
        assert reembed(conn, FakeEmbedder()) == 41
    assert models(landed) == {"fake-hash-384@2"}
    with connect(landed.dsn) as conn:
        with pytest.raises(RuntimeError, match="the index uses"):
            apply_staged(conn, "e1")  # old vectors stay out


# endregion


@pytest.mark.chapter(9)
def test_spark_stage_matches_the_core_stage(landed: Settings) -> None:
    pytest.importorskip("pyspark")
    if shutil.which("java") is None:
        pytest.skip("Spark needs Java")
    from llmdata.embed import spark

    through(landed, "s1", last=5)
    params = {"master": "local[2]", "partitions": 4}
    spark.run(Context("s1", "documents", "60-embed", landed, params))
    with connect(landed.dsn) as conn:
        rows = conn.execute(
            "SELECT text, embedding FROM staged_chunks"
            " WHERE run_id = 's1'"
        ).fetchall()
    want = FakeEmbedder().embed([str(t) for t, _ in rows])
    for (_, got), vec in zip(rows, want, strict=True):
        assert np.allclose(got.to_numpy(), vec)
