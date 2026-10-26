"""Run ledger: open, publish-and-commit, close (Chapter 12)."""

from __future__ import annotations

from llmdata.db import connect
from llmdata.freshness import advance_checkpoints
from llmdata.index.writers import apply_staged
from llmdata.pipeline.context import Context


def open_run(ctx: Context) -> None:
    with connect(ctx.settings.dsn) as conn:
        conn.execute(
            "INSERT INTO ledger (run_id, pipeline, status)"
            " VALUES (%s, %s, 'running') ON CONFLICT (run_id)"
            " DO UPDATE SET status = 'running'",
            (ctx.run_id, ctx.pipeline),
        )


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


def commit(ctx: Context) -> None:
    """Publish and advance checkpoints in one transaction."""
    with connect(ctx.settings.dsn) as conn:
        published = apply_staged(conn, ctx.run_id)
        ctx.pause_point()
        advance_checkpoints(conn, ctx.run_id)
        conn.execute(
            "UPDATE ledger SET status = 'committed'"
            " WHERE run_id = %s",
            (ctx.run_id,),
        )
    print(f"committed {published} documents")


def close_run(ctx: Context) -> None:
    with connect(ctx.settings.dsn) as conn:
        conn.execute(
            "UPDATE ledger SET status = 'succeeded',"
            " finished_at = now() WHERE run_id = %s",
            (ctx.run_id,),
        )
