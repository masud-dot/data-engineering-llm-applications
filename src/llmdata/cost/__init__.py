"""Costs of the data layer: measured, then priced by plan."""

from __future__ import annotations

import argparse
import os
import re
import statistics
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llmdata.chunk import chunk
from llmdata.config import settings
from llmdata.db import Conn, connect
from llmdata.embed import Embedder, get
from llmdata.pipeline import spec

PRICES = Path(__file__).with_name("prices.toml")


@dataclass(frozen=True)
class Facts:
    documents: int
    chunks: int
    chars: int
    bytes: int  # the chunks table with its indexes


MEASURE = (
    "SELECT (SELECT count(*) FROM documents), count(*),"
    " coalesce(sum(length(text)), 0),"
    " pg_total_relation_size('chunks') FROM chunks"
)


def measure(conn: Conn) -> Facts:
    row = conn.execute(MEASURE).fetchone()
    return Facts(*(int(v) for v in row or (0, 0, 0, 0)))


# region: plan
LATEST = (  # each published document's newest cleaned text
    "SELECT cleaned FROM (SELECT DISTINCT ON (s.doc_key) s.doc_key,"
    " s.op, s.cleaned FROM staged s JOIN ledger l USING (run_id)"
    " ORDER BY s.doc_key, l.started_at DESC) latest"
    " JOIN documents USING (doc_key) WHERE op = 'upsert'"
)


def plan(conn: Conn, size: int) -> Facts:
    """The index a chunk size would build, without building it."""
    stages = spec.load(settings().pipelines_dir, "documents")
    rule = next(s.params for s in stages if s.name == "40-chunk")
    heading, now = re.compile(str(rule["headings"])), measure(conn)
    texts = [t or "" for (t,) in conn.execute(LATEST)]
    pieces = [p for t in texts for p in chunk(t, size, heading)]
    chars = sum(len(p.text) for p in pieces)
    fixed = (now.bytes - now.chars) / max(now.chunks, 1)
    stored = int(
        fixed * len(pieces) + chars
    )  # vectors scale by count
    return Facts(len(texts), len(pieces), chars, stored)


# endregion


# region: monthly-cost
def monthly(f: Facts, p: dict[str, Any], k: int) -> dict[str, float]:
    """Pounds a month at production volume, from one index's facts."""
    u = p["usage"]
    rate = {n: v / 1e6 for n, v in p["per_million_tokens"].items()}
    scale = u["documents"] / f.documents  # a projection, not a run
    tokens = f.chars / p["chars_per_token"] * scale
    prompts = (
        u["queries"] * k * f.chars / f.chunks / p["chars_per_token"]
    )
    answers = u["queries"] * u["answer_tokens"]
    return {
        "embedding": tokens * u["changed_share"] * rate["embedding"],
        "storage": f.bytes * scale / 1e9 * p["storage_gb_month"],
        "prompts": prompts * rate["prompt"],
        "answers": answers * rate["answer"],
    }


def reembed(f: Facts, p: dict[str, Any]) -> float:
    """Pounds to embed the whole index once, at production volume."""
    scale = int(p["usage"]["documents"]) / f.documents
    tokens = f.chars / float(p["chars_per_token"]) * scale
    return tokens * float(p["per_million_tokens"]["embedding"]) / 1e6


# endregion


# region: bench
QUESTIONS = (
    "SELECT question, region, role FROM evals.items"
    " ORDER BY version DESC, item_id LIMIT %s"
)
SEARCH = "SELECT * FROM hybrid_search(%s, %s, %s, %s, %s)"


def bench(
    conn: Conn, embedder: Embedder, n: int = 40, k: int = 5
) -> dict[str, float]:
    """Milliseconds per question, embedding plus search."""
    times = []
    for question, region, role in conn.execute(QUESTIONS, (n,)):
        start = time.perf_counter()
        [vector] = embedder.embed([question])
        conn.execute(SEARCH, (question, vector, region, role, k))
        times.append((time.perf_counter() - start) * 1000)
    cuts = statistics.quantiles(times, n=20)
    return {
        "questions": len(times),
        "p50_ms": round(statistics.median(times), 1),
        "p95_ms": round(cuts[18], 1),
    }


# endregion


def cell(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def table(rows: list[tuple[str, Any, Any]]) -> str:
    return "\n".join(
        f"{a:<22}{cell(b):>12}{cell(c):>12}" for a, b, c in rows
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.cost")
    parser.add_argument("command", choices=["estimate", "bench"])
    parser.add_argument("--size", type=int, help="planned chunk size")
    parser.add_argument(
        "--k", type=int, help="planned chunks a prompt"
    )
    args = parser.parse_args(argv)
    prices = tomllib.loads(PRICES.read_text())
    with connect(settings().dsn) as conn:
        if args.command == "bench":
            embedder = get(os.environ.get("EMBEDDER", "fake"))
            print(bench(conn, embedder))
            return 0
        now = measure(conn)
        new = plan(conn, args.size) if args.size else now
    k = prices["usage"]["k"]
    a, b = monthly(now, prices, k), monthly(new, prices, args.k or k)
    rows: list[tuple[str, Any, Any]] = [("", "now", "planned")]
    rows += [("chunks", now.chunks, new.chunks)]
    rows += [("characters", now.chars, new.chars)]
    rows += [("stored MB", now.bytes / 1e6, new.bytes / 1e6)]
    rows += [(f"\u00a3/month {n}", a[n], b[n]) for n in a]
    rows += [("\u00a3/month total", sum(a.values()), sum(b.values()))]
    rows += [
        (
            "\u00a3 re-embed, once",
            reembed(now, prices),
            reembed(new, prices),
        )
    ]
    print(table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
