"""Backfill: re-stage documents that older code published."""

from __future__ import annotations

import os

from psycopg.types.json import Jsonb

from llmdata.contracts import SourceItem
from llmdata.db import connect
from llmdata.ingest import STAGE
from llmdata.ingest.sources import (
    claim_item,
    claim_rows,
    file_item,
    file_manifest,
)
from llmdata.pipeline import spec
from llmdata.pipeline.context import Context

# region: backfill-select
OLDER_CODE = (
    "SELECT d.doc_key, d.version FROM documents d"
    " LEFT JOIN ledger l ON l.run_id = d.run_id"
    " WHERE l.code IS DISTINCT FROM ("
    "   SELECT code FROM ledger WHERE run_id = %(run)s)"
    " AND (%(origin)s = '' OR d.origin = %(origin)s)"
    " ORDER BY d.doc_key"
)
# endregion


# region: backfill-stage
def run(ctx: Context) -> None:
    """Stage one batch of documents that other code published."""
    scope = ctx.conf.get("backfill")
    if scope is None:
        return
    batch = int(
        scope.get("batch")
        or spec.policy(
            ctx.settings.pipelines_dir,
            os.environ.get("LLMDATA_UNTIL"),
        ).backfill_batch
    )
    origin = str(scope.get("origin") or "")
    files = file_manifest(ctx.settings.data_dir)
    claims = {
        f"claim:{r.claim_id}": r
        for r in claim_rows(ctx.settings.source_dsn, live_only=True)
    }
    with connect(ctx.settings.dsn) as conn:
        todo = conn.execute(
            OLDER_CODE, {"run": ctx.run_id, "origin": origin}
        ).fetchall()
        staged = 0
        for key, version in todo[:batch]:
            item: SourceItem | None = None
            if key in files:
                item = file_item(key, files[key])
            elif key in claims:
                item = claim_item(claims[key])
            if item is None or item.content_hash[:16] != version:
                continue  # changed or gone: this run's ingest has it
            row = item.model_dump() | {"run_id": ctx.run_id}
            done = conn.execute(
                STAGE + " ON CONFLICT (run_id, doc_key) DO NOTHING",
                row | {"meta": Jsonb(item.meta)},
            )
            staged += done.rowcount
    left = max(len(todo) - batch, 0)
    print(f"backfill: {staged} documents staged, {left} still to do")


# endregion
