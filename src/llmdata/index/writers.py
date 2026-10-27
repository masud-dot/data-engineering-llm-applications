"""Apply staged documents to the live index."""

from __future__ import annotations

from typing import Any

from llmdata.db import Conn, connect
from llmdata.pipeline.context import Context


def staged_docs(conn: Conn, run_id: str) -> list[tuple[Any, ...]]:
    return conn.execute(
        "SELECT doc_key, op FROM staged WHERE run_id = %s"
        " ORDER BY doc_key",
        (run_id,),
    ).fetchall()


def apply_doc(conn: Conn, run_id: str, key: str, op: str) -> None:
    """Replace one document; the caller owns the transaction."""
    conn.execute("DELETE FROM documents WHERE doc_key = %s", (key,))
    if op == "delete":
        conn.execute(
            "INSERT INTO tombstones (doc_key, run_id, reason)"
            " VALUES (%s, %s, 'deleted') ON CONFLICT DO NOTHING",
            (key, run_id),
        )
        return
    conn.execute(
        "INSERT INTO documents (doc_key, doc_id, version, origin,"
        " meta, run_id) SELECT doc_key, doc_id, version, origin,"
        " meta, run_id FROM staged WHERE run_id = %s"
        " AND doc_key = %s",
        (run_id, key),
    )
    conn.execute(
        "INSERT INTO chunks (chunk_id, doc_key, ordinal, section,"
        " text, embedding, embedding_model, meta, run_id)"
        " SELECT c.chunk_id, c.doc_key, c.ordinal, c.section, c.text,"
        " c.embedding, c.embedding_model, s.meta - 'minhash',"
        " c.run_id"
        " FROM staged_chunks c JOIN staged s"
        " USING (run_id, doc_key)"
        " WHERE c.run_id = %s AND c.doc_key = %s",
        (run_id, key),
    )


def check_models(conn: Conn, run_id: str) -> None:
    """Never publish vectors from a model the index does not use."""
    staged = {
        str(m)
        for (m,) in conn.execute(
            "SELECT DISTINCT embedding_model FROM staged_chunks"
            " WHERE run_id = %s AND embedding_model IS NOT NULL",
            (run_id,),
        )
    }
    live = {
        str(m)
        for (m,) in conn.execute(
            "SELECT DISTINCT embedding_model FROM chunks"
        )
    }
    if live and staged - live:
        raise RuntimeError(
            f"run {run_id} has vectors from {sorted(staged - live)};"
            f" the index uses {sorted(live)}"
        )


def apply_staged(conn: Conn, run_id: str) -> int:
    check_models(conn, run_id)
    docs = staged_docs(conn, run_id)
    for key, op in docs:
        apply_doc(conn, run_id, key, op)
    return len(docs)


class DirectWriter:
    """One transaction per document (Chapter 10)."""

    def __call__(self, ctx: Context) -> int:
        with connect(ctx.settings.dsn) as conn:
            check_models(conn, ctx.run_id)
            docs = staged_docs(conn, ctx.run_id)
            for key, op in docs:
                apply_doc(conn, ctx.run_id, key, op)
                conn.commit()
        return len(docs)
