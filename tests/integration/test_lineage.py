"""Lineage: every chunk ID leads back to its version and its bytes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from llmdata import chunk, clean, identity, ingest, parse
from llmdata.config import Settings
from llmdata.db import connect
from llmdata.identity import trace
from llmdata.pipeline.context import Context
from llmdata.pipeline.spec import load

GUIDE = "file:guidelines/south/GL-0001.html"
STAGES = (
    (ingest, "10-ingest"),
    (parse, "20-parse"),
    (clean, "30-clean"),
    (chunk, "40-chunk"),
    (identity, "50-identity"),
)


def through(cfg: Settings, run_id: str, last: str) -> None:
    """Run the stages of the documents pipeline, up to last."""
    stages = load(Path("pipelines"), "documents")
    params = {s.name: s.params for s in stages}
    for module, name in STAGES:
        module.run(
            Context(run_id, "documents", name, cfg, params[name])
        )
        if name == last:
            return


def chunk_ids(cfg: Settings, run_id: str, key: str) -> list[str]:
    with connect(cfg.dsn) as conn:
        rows = conn.execute(
            "SELECT chunk_id FROM staged_chunks WHERE run_id = %s"
            " AND doc_key = %s ORDER BY ordinal",
            (run_id, key),
        )
        return [str(r[0]) for r in rows]


# region: lineage-test
@pytest.mark.chapter(8)
def test_an_old_chunk_still_traces_to_its_bytes(
    landed: Settings,
) -> None:
    through(landed, "v1", "50-identity")
    page = landed.data_dir / "landing" / GUIDE.removeprefix("file:")
    page.write_text(page.read_text() + "<p>Revised in March.</p>")
    through(landed, "v2", "50-identity")
    old, new = (
        chunk_ids(landed, "v1", GUIDE),
        chunk_ids(landed, "v2", GUIDE),
    )
    assert (
        old[0].split(":")[0] == new[0].split(":")[0]
    )  # same document
    assert old[0].split(":")[1] != new[0].split(":")[1]  # new version
    with connect(
        landed.dsn
    ) as conn:  # publish v2, as Chapter 10 will
        conn.execute(
            "INSERT INTO documents (doc_key, doc_id, version, origin,"
            " meta, run_id) SELECT doc_key, doc_id, version, origin,"
            " meta, run_id FROM staged WHERE run_id = 'v2'"
        )
        then = trace(conn, old[0], landed.data_dir / "archive")
    assert then["document"] == GUIDE and not then["current"]
    kept = Path(then["archived"]).read_bytes()
    assert hashlib.sha256(kept).hexdigest()[:16] == then["version"]
    assert b"Revised in March" not in kept


@pytest.mark.chapter(8)
def test_content_changed_mid_run_is_refused(landed: Settings) -> None:
    through(landed, "v1", "40-chunk")
    page = landed.data_dir / "landing" / GUIDE.removeprefix("file:")
    page.write_text(page.read_text() + "<p>Edited too late.</p>")
    stage = Context("v1", "documents", "50-identity", landed)
    with pytest.raises(RuntimeError, match="changed after ingestion"):
        identity.run(stage)


# endregion
