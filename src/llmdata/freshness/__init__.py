"""Reconciliation and checkpoint commits (Chapter 11)."""

from __future__ import annotations

import argparse
import json

from psycopg.types.json import Jsonb

from llmdata.config import settings
from llmdata.db import Conn, connect
from llmdata.ingest.sources import (
    claim_item,
    claim_rows,
    file_manifest,
)
from llmdata.pipeline.context import Context


def reconcile(ctx: Context) -> None:
    """Stage deletes for indexed documents gone from every source."""
    with connect(ctx.settings.source_dsn, vectors=False) as src:
        keys = {
            f"claim:{row[0]}"
            for row in src.execute("SELECT claim_id FROM claims")
        }
    keys |= set(file_manifest(ctx.settings.data_dir))
    with connect(ctx.settings.dsn) as conn:
        indexed: dict[str, str] = {
            str(k): str(v)
            for k, v in conn.execute(
                "SELECT doc_key, origin FROM documents"
            )
        }
        staged = {
            row[0]
            for row in conn.execute(
                "SELECT doc_key FROM staged WHERE run_id = %s",
                (ctx.run_id,),
            )
        }
        orphans = sorted(set(indexed) - keys - staged)
        for key in orphans:
            conn.execute(
                "INSERT INTO staged (run_id, doc_key, op, origin,"
                " kind, meta) VALUES"
                " (%s, %s, 'delete', %s, 'record', %s)",
                (ctx.run_id, key, indexed[key], Jsonb({})),
            )
    print(f"reconcile: {len(orphans)} orphaned documents staged")


def advance_checkpoints(conn: Conn, run_id: str) -> None:
    conn.execute(
        "INSERT INTO checkpoints"
        " (source, watermark, manifest, run_id, committed_at)"
        " SELECT source, watermark, manifest, run_id, now()"
        " FROM pending_checkpoints WHERE run_id = %s"
        " ON CONFLICT (source) DO UPDATE SET"
        " watermark = EXCLUDED.watermark,"
        " manifest = EXCLUDED.manifest,"
        " run_id = EXCLUDED.run_id, committed_at = now()",
        (run_id,),
    )


def commit(ctx: Context) -> None:
    with connect(ctx.settings.dsn) as conn:
        advance_checkpoints(conn, ctx.run_id)
    print("checkpoints advanced")


def show() -> dict[str, object]:
    with connect(settings().dsn) as conn:
        rows = conn.execute(
            "SELECT source, watermark, md5(manifest::text)"
            " FROM checkpoints ORDER BY source"
        ).fetchall()
    return {str(s): [str(w), str(m)] for s, w, m in rows}


def compare() -> dict[str, object]:
    """The live index against every source: keys and versions."""
    cfg = settings()
    want = {
        k: v[0][:16] for k, v in file_manifest(cfg.data_dir).items()
    }
    for record in claim_rows(cfg.source_dsn, live_only=True):
        item = claim_item(record)
        want[item.doc_key] = item.content_hash[:16]
    with connect(cfg.dsn) as conn:
        have = {
            str(k): str(v)
            for k, v in conn.execute(
                "SELECT doc_key, version FROM documents"
            )
        }
        empty = conn.execute(
            "SELECT count(*) FROM documents d WHERE NOT EXISTS"
            " (SELECT 1 FROM chunks c WHERE c.doc_key = d.doc_key)"
        ).fetchone()
    report: dict[str, object] = {
        "expected": len(want),
        "indexed": len(have),
        "missing": len(set(want) - set(have)),
        "extra": len(set(have) - set(want)),
        "stale": sum(
            1 for k in want if k in have and have[k] != want[k]
        ),
        "without_chunks": int(empty[0]) if empty else 0,
    }
    report["match"] = not any(
        report[k]
        for k in ("missing", "extra", "stale", "without_chunks")
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.freshness")
    parser.add_argument("command", choices=["show", "compare"])
    args = parser.parse_args(argv)
    if args.command == "show":
        print(json.dumps(show(), sort_keys=True))
        return 0
    report = compare()
    print(json.dumps(report, sort_keys=True))
    return 0 if report["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
