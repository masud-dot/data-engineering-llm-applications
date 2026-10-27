"""Reconciliation and checkpoint commits (Chapter 11)."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from llmdata.config import settings
from llmdata.db import Conn, connect
from llmdata.freshness.sources import erased, guard, limit
from llmdata.ingest.sources import (
    claim_item,
    claim_rows,
    file_manifest,
    sha256,
)
from llmdata.pipeline.context import Context

SLAS = Path(__file__).parents[1] / "contracts" / "slas.toml"


def source_of(origin: str) -> str:
    return "claims" if origin == "claims" else "landing zone"


# region: reconcile
def reconcile(ctx: Context) -> None:
    """Stage deletes for indexed documents gone from every source."""
    with connect(ctx.settings.source_dsn, vectors=False) as src:
        keys = {
            f"claim:{row[0]}"
            for row in src.execute("SELECT claim_id FROM claims")
        }
    keys |= set(file_manifest(ctx.settings.data_dir))
    with connect(ctx.settings.dsn) as conn:
        indexed: dict[str, str] = dict(
            conn.execute("SELECT doc_key, origin FROM documents")
        )
        staged = {
            row[0]
            for row in conn.execute(
                "SELECT doc_key FROM staged WHERE run_id = %s",
                (ctx.run_id,),
            )
        }
        orphans = sorted(set(indexed) - keys - staged)
        have = Counter(map(source_of, indexed.values()))
        lost = Counter(source_of(indexed[key]) for key in orphans)
        for name, gone in lost.items():
            guard(name, have[name], gone, limit(ctx))
        for key in orphans:
            conn.execute(
                "INSERT INTO staged (run_id, doc_key, op, origin,"
                " kind, meta) VALUES"
                " (%s, %s, 'delete', %s, 'record', %s)",
                (ctx.run_id, key, indexed[key], Jsonb({})),
            )
    print(f"reconcile: {len(orphans)} orphaned documents staged")


# endregion


def advance_checkpoints(conn: Conn, run_id: str) -> None:
    conn.execute(
        "INSERT INTO checkpoints (source, watermark, manifest,"
        " run_id, read_at, committed_at)"
        " SELECT source, watermark, manifest, run_id, read_at,"
        " now() FROM pending_checkpoints WHERE run_id = %s"
        " ON CONFLICT (source) DO UPDATE SET"
        " watermark = EXCLUDED.watermark,"
        " manifest = EXCLUDED.manifest, run_id = EXCLUDED.run_id,"
        " read_at = EXCLUDED.read_at, committed_at = now()",
        (run_id,),
    )


def commit(ctx: Context) -> None:
    with connect(ctx.settings.dsn) as conn:
        advance_checkpoints(conn, ctx.run_id)
    print("checkpoints advanced")


# region: erase
def erase(key: str, request: str) -> dict[str, int]:
    """Remove a document and its copies from every store we own."""
    cfg = settings()
    removed: Counter[str] = Counter()
    with connect(cfg.dsn) as conn:  # one transaction
        keys = [key] + [
            str(k)
            for (k,) in conn.execute(
                "SELECT doc_key FROM documents"
                " WHERE meta -> 'duplicate_of' ->> 'doc_key' = %s",
                (key,),
            )
        ]
        texts = conn.execute(
            "SELECT text FROM chunks WHERE doc_key = ANY(%(k)s)"
            " UNION SELECT text FROM staged_chunks"
            " WHERE doc_key = ANY(%(k)s)",
            {"k": keys},
        )
        hashes = [sha256(str(t).encode()) for (t,) in texts]
        digests = {
            str(d)
            for (d,) in conn.execute(
                "SELECT content_hash FROM versions"
                " WHERE doc_key = ANY(%s)",
                (keys,),
            )
        }
        for table in (
            "documents",
            "staged_chunks",
            "staged",
            "versions",
        ):
            removed[table] = conn.execute(
                f"DELETE FROM {table} WHERE doc_key = ANY(%s)",
                (keys,),
            ).rowcount
        removed["embedding_cache"] = conn.execute(
            "DELETE FROM embedding_cache WHERE text_hash = ANY(%s)",
            (hashes,),
        ).rowcount
        conn.execute(
            "INSERT INTO tombstones (doc_key, run_id, reason,"
            " request) SELECT k, %s, 'erased', %s"
            " FROM unnest(%s::text[]) AS k ON CONFLICT DO NOTHING",
            (f"erase:{request}", request, keys),
        )
        shared = {
            str(d)
            for (d,) in conn.execute(
                "SELECT content_hash FROM versions"
                " WHERE content_hash = ANY(%s)",
                (sorted(digests),),
            )
        }
        paths = [
            cfg.data_dir / "archive" / d[:2] / d
            for d in digests - shared
        ] + [
            cfg.data_dir / "landing" / k.split(":", 1)[1]
            for k in keys
            if k.startswith("file:")
        ]
        for path in paths:  # before the commit: a rerun finishes
            if path.exists():
                path.unlink()
                removed["files"] += 1
    return dict(removed)


# endregion


# region: lag
def seconds(duration: str) -> int:
    """Days, hours and minutes of an ISO 8601 duration."""
    unit = {"D": 86400, "H": 3600, "M": 60}
    found = re.findall(r"(\d+)([DHM])", duration)
    return sum(int(n) * unit[u] for n, u in found)


def lag() -> dict[str, Any]:
    """Each source's lag: the age of its last committed read."""
    with SLAS.open("rb") as fh:
        slas = tomllib.load(fh)
    with connect(settings().dsn) as conn:
        ages = {
            str(name): float(age)
            for name, age in conn.execute(
                "SELECT source,"
                " extract(epoch FROM now() - read_at)"
                " FROM checkpoints WHERE read_at IS NOT NULL"
            )
        }
    report: dict[str, Any] = {}
    for name, sla in slas.items():
        age = ages.get("claims" if name == "claims" else "files")
        target = min(
            seconds(sla["max_lag"]), seconds(sla["delete_within"])
        )
        report[name] = {
            "lag": str(timedelta(seconds=round(age)))
            if age is not None
            else None,
            "target": str(timedelta(seconds=target)),
            "ok": age is not None and age <= target,
        }
    return report


# endregion


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
        gone = erased(conn) & set(want)
        for key in gone:  # the source must erase these too
            del want[key]
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
        "erased_at_source": len(gone),
    }
    report["match"] = not any(
        report[k]
        for k in ("missing", "extra", "stale", "without_chunks")
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.freshness")
    parser.add_argument(
        "command", choices=["show", "compare", "lag", "erase"]
    )
    parser.add_argument("key", nargs="?")
    parser.add_argument("--request", default="")
    args = parser.parse_args(argv)
    if args.command == "erase":
        if not args.key or not args.request:
            parser.error("erase needs a key and --request")
        print(json.dumps(erase(args.key, args.request)))
        return 0
    report = {"show": show, "compare": compare, "lag": lag}[
        args.command
    ]()
    print(json.dumps(report, sort_keys=True))
    if args.command == "show":
        return 0
    if args.command == "compare":
        return 0 if report["match"] else 1
    return 0 if all(v["ok"] for v in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
