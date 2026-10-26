"""Identity stage: stable document IDs, versions and chunk IDs."""

from __future__ import annotations

from llmdata.db import connect
from llmdata.pipeline.context import Context


def run(ctx: Context) -> None:
    with connect(ctx.settings.dsn) as conn:
        conn.execute(
            "UPDATE staged SET doc_id = left(encode(sha256("
            "convert_to(origin || '|' || doc_key, 'UTF8')),"
            " 'hex'), 16),"
            " version = left(content_hash, 16)"
            " WHERE run_id = %s AND op = 'upsert'",
            (ctx.run_id,),
        )
        done = conn.execute(
            "UPDATE staged_chunks c SET chunk_id = s.doc_id || ':'"
            " || s.version || ':' || lpad(c.ordinal::text, 4, '0')"
            " FROM staged s WHERE s.run_id = c.run_id"
            " AND s.doc_key = c.doc_key AND c.run_id = %s",
            (ctx.run_id,),
        )
    print(f"identified {done.rowcount} chunks")
