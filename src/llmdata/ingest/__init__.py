"""Ingest stage: stage this run's changes from a change source."""

from __future__ import annotations

from collections import Counter

from psycopg.types.json import Jsonb

from llmdata.db import Conn, connect
from llmdata.loader import load_object
from llmdata.pipeline.context import Context

DEFAULT = "llmdata.ingest.sources:SnapshotSource"


# region: ingest-stage
STAGE = (
    "INSERT INTO staged (run_id, doc_key, op, origin, kind,"
    " content_hash, ref, raw, meta) VALUES (%(run_id)s,"
    " %(doc_key)s, %(op)s, %(origin)s, %(kind)s,"
    " %(content_hash)s, %(ref)s, %(raw)s, %(meta)s)"
)


def clear(conn: Conn, run_id: str) -> None:
    """Remove whatever an earlier attempt of this run staged."""
    for table in ("staged_chunks", "staged", "pending_checkpoints"):
        conn.execute(
            f"DELETE FROM {table} WHERE run_id = %s", (run_id,)
        )


def run(ctx: Context) -> None:
    source = load_object(ctx.params.get("source", DEFAULT))()
    counts: Counter[str] = Counter()
    with connect(ctx.settings.dsn) as conn:  # one transaction
        clear(conn, ctx.run_id)
        for item in source.changes(ctx, conn):
            row = item.model_dump() | {"run_id": ctx.run_id}
            conn.execute(STAGE, row | {"meta": Jsonb(item.meta)})
            counts[item.op] += 1
        for name, (mark, manifest) in source.pending().items():
            conn.execute(
                "INSERT INTO pending_checkpoints (run_id, source,"
                " watermark, manifest) VALUES (%s, %s, %s, %s)",
                (ctx.run_id, name, mark, Jsonb(manifest)),
            )
    print(f"staged {dict(counts) or 'no changes'}")


# endregion
