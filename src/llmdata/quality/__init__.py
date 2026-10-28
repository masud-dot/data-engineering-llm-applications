"""Quality gate on staged data, before anything is published."""

from __future__ import annotations

import argparse
import json
from typing import Any

from llmdata.config import settings
from llmdata.db import Conn, connect
from llmdata.pipeline.context import Context
from llmdata.quality.checks import Result, counts, drift, profile
from llmdata.quality.contracts import violations

DEFAULTS: dict[str, Any] = {
    "max_chunk_chars": 2000,
    "max_shrink": 0.3,
    "min_chars": 100,
    "max_near_empty": 0.02,
    "min_docs": 20,
    "window": 5,
    "max_change": 0.3,
    "max_share_change": 0.15,
}


class QualityError(RuntimeError):
    """The run failed its quality gate; nothing was published."""


def store(
    conn: Conn, run_id: str, results: list[Result], accept: set[str]
) -> None:
    conn.execute(
        "DELETE FROM quality_results WHERE run_id = %s", (run_id,)
    )
    for r in results:
        conn.execute(
            "INSERT INTO quality_results (run_id, name, scope, value,"
            " bound, passed, accepted) VALUES (%s, %s, %s, %s, %s,"
            " %s, %s)",
            (
                run_id,
                r.name,
                r.scope,
                r.value,
                r.bound,
                r.passed,
                not r.passed and r.name in accept,
            ),
        )


# region: quality-gate
def gate(ctx: Context) -> None:
    """Check the run; record every result; stop if one fails."""
    p = DEFAULTS | ctx.params
    accept = set(ctx.conf.get("accept", []))
    landing = ctx.settings.data_dir / "landing"
    with connect(ctx.settings.dsn) as conn:
        results = counts(conn, ctx.run_id, p)
        broken = violations(conn, ctx.run_id)
        results.append(
            Result(
                "contract violations", "", len(broken), 0, not broken
            )
        )
        now = profile(conn, ctx.run_id, landing)
        results += drift(conn, now, p)
        results += [  # measures, kept as the next runs' baseline
            Result(name, scope, value, None, True)
            for (name, scope), value in now.items()
        ]
        store(conn, ctx.run_id, results, accept)
    failed = [
        r for r in results if not r.passed and r.name not in accept
    ]
    for r in failed:
        where = f" ({r.scope})" if r.scope else ""
        print(
            f"FAILED {r.name}{where}: {r.value:.3g}, bound {r.bound}"
        )
    if failed:
        raise QualityError(f"{len(failed)} quality checks failed")
    print(f"quality gate passed: {len(results)} results recorded")


# endregion


# region: index-check
SAMPLE = (
    "SELECT chunk_id, embedding, region, roles[1]"
    " FROM search_chunks ORDER BY md5(chunk_id) LIMIT %s"
)


def index_check(size: int = 50, k: int = 5) -> dict[str, Any]:
    """Can search() find a sample of chunks by their own vectors?"""
    with connect(settings().dsn) as conn:
        rows = conn.execute(SAMPLE, (size,)).fetchall()
        found = 0
        for chunk_id, vector, region, role in rows:
            hits = conn.execute(
                "SELECT chunk_id FROM search(%s, %s, %s, %s)",
                (vector, region, role, k),
            ).fetchall()
            found += (chunk_id,) in hits
    recall = found / len(rows) if rows else 1.0
    return {"sampled": len(rows), "found": found, "recall": recall}


# endregion


def report(run_id: str | None) -> list[tuple[Any, ...]]:
    with connect(settings().dsn) as conn:
        return conn.execute(
            "SELECT name, scope, round(value::numeric, 3), bound,"
            " passed, accepted FROM quality_results"
            " WHERE run_id = coalesce(%s, (SELECT run_id FROM ledger"
            " ORDER BY started_at DESC LIMIT 1))"
            " ORDER BY passed, name, scope",
            (run_id,),
        ).fetchall()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.quality")
    parser.add_argument("command", choices=["report", "index"])
    parser.add_argument("run_id", nargs="?")
    args = parser.parse_args(argv)
    if args.command == "index":
        result = index_check()
        print(json.dumps(result))
        return 0 if result["recall"] >= 0.98 else 1
    for row in report(args.run_id):
        print("  ".join("-" if v is None else str(v) for v in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
