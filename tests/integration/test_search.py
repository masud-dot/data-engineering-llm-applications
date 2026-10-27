"""Search: access filters inside the index, k rows, exact words."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llmdata import chunk, clean, embed, identity, ingest, parse
from llmdata.config import Settings
from llmdata.db import Conn, connect
from llmdata.index.writers import apply_staged
from llmdata.pipeline.context import Context
from llmdata.pipeline.spec import load

GUIDE = "file:guidelines/south/GL-0001.html"  # underwriters, South
WELSH = "file:emails/north/EM-0004.eml"  # claims staff, North
STAGES = (ingest, parse, clean, chunk, identity, embed)
NUMBERS = ("10", "20", "30", "40", "50", "60")


def publish(cfg: Settings) -> None:
    """Run the stages up to embedding, then load the index."""
    stages = load(Path("pipelines"), "documents", "ch10")
    params = {s.name: s.params for s in stages}
    names = [n for n in params if n[:2] in NUMBERS]
    for module, name in zip(STAGES, names, strict=True):
        module.run(
            Context("q1", "documents", name, cfg, params[name])
        )
    with connect(cfg.dsn) as conn:
        apply_staged(conn, "q1")


def vector(conn: Conn, key: str) -> Any:
    row = conn.execute(
        "SELECT embedding FROM chunks WHERE doc_key = %s"
        " ORDER BY ordinal LIMIT 1",
        (key,),
    ).fetchone()
    assert row is not None
    return row[0]


# region: search-tests
@pytest.mark.chapter(10)
def test_search_keeps_to_region_and_role(landed: Settings) -> None:
    publish(landed)
    with connect(landed.dsn) as conn:
        probe = vector(conn, GUIDE)

        def found(region: str, role: str) -> list[str]:
            rows = conn.execute(
                "SELECT doc_key FROM search(%s, %s, %s, 50)",
                (probe, region, role),
            )
            return [str(r[0]) for r in rows]

        assert found("south", "underwriter")[0] == GUIDE
        assert GUIDE not in found("north", "underwriter")
        assert GUIDE not in found("south", "claims")


@pytest.mark.chapter(10)
def test_strict_filters_still_fill_k(landed: Settings) -> None:
    publish(landed)
    with connect(landed.dsn) as conn:
        conn.execute("SET enable_seqscan = off")  # use the HNSW index
        conn.execute(
            "SET hnsw.ef_search = 1"
        )  # one candidate per step
        allowed = conn.execute(
            "SELECT count(*) FROM search_chunks"
            " WHERE region = 'south' AND 'claims' = ANY (roles)"
        ).fetchone()
        assert allowed is not None and allowed[0] > 1
        rows = conn.execute(
            "SELECT * FROM search(%s, 'south', 'claims', %s)",
            (vector(conn, GUIDE), allowed[0]),
        ).fetchall()
        assert len(rows) == allowed[0]


# endregion


@pytest.mark.chapter(10)
def test_hybrid_search_lifts_exact_words(landed: Settings) -> None:
    publish(landed)
    with connect(landed.dsn) as conn:
        rows = conn.execute(
            "SELECT doc_key FROM hybrid_search(%s, %s, %s, %s)",
            ("yswiriant", vector(conn, GUIDE), "north", "claims"),
        ).fetchall()
    assert rows[0][0] == WELSH
