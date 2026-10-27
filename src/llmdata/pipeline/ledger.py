"""Run ledger: open, publish-and-commit, close (Chapter 12)."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from psycopg.types.json import Jsonb

from llmdata.config import settings
from llmdata.db import Conn, connect
from llmdata.freshness import advance_checkpoints
from llmdata.index.writers import apply_staged
from llmdata.pipeline import spec
from llmdata.pipeline.context import Context

PACKAGE = Path(__file__).parents[1]
STAGING = ("staged_chunks", "staged", "pending_checkpoints")


def fingerprint(pipelines: Path) -> str:
    """The code a run executes: every module and every TOML file."""
    digest = hashlib.sha256()
    files = [(PACKAGE, p) for p in PACKAGE.rglob("*.py")]
    files += [(pipelines, p) for p in pipelines.rglob("*.toml")]
    for base, path in sorted(files, key=lambda f: f[1]):
        digest.update(str(path.relative_to(base)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def drop_staged(conn: Conn, runs: list[str]) -> None:
    for table in STAGING:
        conn.execute(
            f"DELETE FROM {table} WHERE run_id = ANY(%s)", (runs,)
        )


# region: ledger-open
def open_run(ctx: Context) -> None:
    """Record this run; abandon unfinished runs of the pipeline."""
    scope = ctx.conf.get("backfill")
    with connect(ctx.settings.dsn) as conn:
        stale = [
            str(r)
            for (r,) in conn.execute(
                "UPDATE ledger SET status = 'abandoned',"
                " finished_at = now() WHERE pipeline = %s"
                " AND status = 'running' AND run_id <> %s"
                " RETURNING run_id",
                (ctx.pipeline, ctx.run_id),
            )
        ]
        drop_staged(conn, stale)  # their checkpoints never moved
        conn.execute(
            "INSERT INTO ledger (run_id, pipeline, status, kind,"
            " code, scope) VALUES (%s, %s, 'running', %s, %s, %s)"
            " ON CONFLICT (run_id) DO UPDATE SET"
            " status = 'running', code = EXCLUDED.code",
            (
                ctx.run_id,
                ctx.pipeline,
                "incremental" if scope is None else "backfill",
                fingerprint(ctx.settings.pipelines_dir),
                Jsonb(scope or {}),
            ),
        )
    print(f"run {ctx.run_id} open; abandoned {stale or 'none'}")


# endregion


class DeferredWriter:
    """Leaves staged documents in place; commit() publishes them."""

    def __call__(self, ctx: Context) -> int:
        with connect(ctx.settings.dsn) as conn:
            row = conn.execute(
                "SELECT count(*) FROM staged WHERE run_id = %s",
                (ctx.run_id,),
            ).fetchone()
        count = int(row[0]) if row else 0
        print(f"{count} documents staged for commit")
        return count


# region: ledger-commit
def commit(ctx: Context) -> None:
    """Publish, move checkpoints and record it in one transaction."""
    with connect(ctx.settings.dsn) as conn:
        row = conn.execute(
            "SELECT status FROM ledger WHERE run_id = %s FOR UPDATE",
            (ctx.run_id,),
        ).fetchone()
        if row and row[0] == "committed":
            print("already committed")  # a retry after success
            return
        if not row or row[0] != "running":
            raise RuntimeError(
                f"run {ctx.run_id} is {row}; not published"
            )
        published = apply_staged(conn, ctx.run_id)
        ctx.pause_point()
        advance_checkpoints(conn, ctx.run_id)
        conn.execute(
            "UPDATE ledger SET status = 'committed', published = %s,"
            " committed_at = now() WHERE run_id = %s",
            (published, ctx.run_id),
        )
    print(f"committed {published} documents")


# endregion


def close_run(ctx: Context) -> None:
    """Mark the run good; keep staged rows of the last few runs."""
    rules = spec.policy(
        ctx.settings.pipelines_dir, os.environ.get("LLMDATA_UNTIL")
    )
    with connect(ctx.settings.dsn) as conn:
        conn.execute(
            "UPDATE ledger SET status = 'succeeded',"
            " finished_at = now() WHERE run_id = %s",
            (ctx.run_id,),
        )
        if rules.keep_staged_runs is None:
            return
        old = [
            str(r)
            for (r,) in conn.execute(
                "SELECT run_id FROM ledger WHERE pipeline = %s"
                " AND status = 'succeeded'"
                " ORDER BY finished_at DESC OFFSET %s",
                (ctx.pipeline, rules.keep_staged_runs),
            )
        ]
        drop_staged(conn, old)


def show(limit: int = 10) -> list[tuple[object, ...]]:
    with connect(settings().dsn) as conn:
        return conn.execute(
            "SELECT run_id, kind, status, code, published,"
            " to_char(started_at, 'HH24:MI'),"
            " to_char(finished_at - started_at, 'MI:SS')"
            " FROM ledger ORDER BY started_at DESC LIMIT %s",
            (limit,),
        ).fetchall()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.pipeline.ledger")
    parser.add_argument("command", choices=["show"])
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    for row in reversed(show(args.limit)):
        print("  ".join("-" if v is None else str(v) for v in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
