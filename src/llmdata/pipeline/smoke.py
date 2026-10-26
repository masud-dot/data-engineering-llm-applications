"""Chapter 3's one-stage skeleton pipeline, and a retry demo."""

from __future__ import annotations

from llmdata.db import connect
from llmdata.pipeline.context import Context


def run(ctx: Context) -> None:
    for dsn in (ctx.settings.dsn, ctx.settings.source_dsn):
        with connect(dsn, vectors=False) as conn:
            conn.execute("SELECT 1")
    print("smoke: both databases reachable")


def fail_once(ctx: Context) -> None:
    if ctx.try_number == 1:
        raise RuntimeError("planned failure on the first attempt")
    print(f"succeeded on attempt {ctx.try_number}")
