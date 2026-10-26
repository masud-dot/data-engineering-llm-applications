"""Quality gate on staged data, before anything is published."""

from __future__ import annotations

from llmdata.db import connect
from llmdata.pipeline.context import Context
from llmdata.quality.contracts import violations

CHECKS = {
    "documents without chunks": (
        "SELECT count(*) FROM staged s WHERE s.run_id = %(r)s"
        " AND s.op = 'upsert' AND NOT EXISTS (SELECT 1"
        " FROM staged_chunks c WHERE c.run_id = s.run_id"
        " AND c.doc_key = s.doc_key)"
    ),
    "chunks without vectors": (
        "SELECT count(*) FROM staged_chunks"
        " WHERE run_id = %(r)s AND embedding IS NULL"
    ),
    "chunks without ids": (
        "SELECT count(*) FROM staged_chunks"
        " WHERE run_id = %(r)s AND chunk_id IS NULL"
    ),
}


def gate(ctx: Context) -> None:
    failures: dict[str, int] = {}
    with connect(ctx.settings.dsn) as conn:
        for name, sql in CHECKS.items():
            row = conn.execute(sql, {"r": ctx.run_id}).fetchone()
            if row and row[0]:
                failures[name] = int(row[0])
        broken = violations(conn, ctx.run_id)
        if broken:
            failures["contract violations"] = len(broken)
            for item in broken[:5]:
                print(
                    f"contract: {item.key} {item.field}:"
                    f" {item.message}"
                )
    if failures:
        raise RuntimeError(f"quality gate failed: {failures}")
    print("quality gate passed")
