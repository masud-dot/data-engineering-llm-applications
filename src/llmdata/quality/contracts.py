"""Check staged documents and chunks against their contracts."""

from __future__ import annotations

from typing import Any

from llmdata.contracts import Chunk, Document, Violation, validate
from llmdata.db import Conn


def _rows(conn: Conn, sql: str, run_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, (run_id,))
        names = [d.name for d in cur.description or []]
        return [dict(zip(names, row, strict=True)) for row in cur]


def violations(conn: Conn, run_id: str) -> list[Violation]:
    docs = _rows(
        conn,
        "SELECT doc_key, doc_id, version, origin, meta AS access,"
        " run_id FROM staged WHERE run_id = %s AND op = 'upsert'",
        run_id,
    )
    chunks = _rows(
        conn,
        "SELECT c.chunk_id, c.doc_key, c.ordinal, c.text,"
        " c.embedding, c.embedding_model, s.meta AS access"
        " FROM staged_chunks c JOIN staged s USING (run_id, doc_key)"
        " WHERE c.run_id = %s",
        run_id,
    )
    for row in chunks:
        vec = row["embedding"]
        row["embedding"] = None if vec is None else vec.to_list()
    _, bad_docs = validate(Document, docs, "doc_key")
    _, bad_chunks = validate(Chunk, chunks, "chunk_id")
    return bad_docs + bad_chunks
