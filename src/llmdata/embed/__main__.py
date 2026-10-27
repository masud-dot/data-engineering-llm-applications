"""Command line: re-embed the index, or measure embedding speed."""

from __future__ import annotations

import argparse
import statistics
import time

from llmdata.config import settings
from llmdata.db import connect
from llmdata.embed import get, model_id, reembed


def bench(texts: list[str]) -> None:
    """Chunks per second at three batch sizes, and token counts."""
    for name in ("fake", "local"):
        try:
            embedder = get(name)
        except Exception as exc:  # the local extra may be missing
            print(f"bench: {name} unavailable ({exc})")
            continue
        for size in (16, 64, 256):
            start = time.perf_counter()
            for i in range(0, len(texts), size):
                embedder.embed(texts[i : i + size])
            rate = len(texts) / (time.perf_counter() - start)
            label = f"{model_id(embedder)} batch {size}"
            print(f"bench: {label}: {rate:.0f} chunks/s")
        count = getattr(embedder, "token_count", None)
        if count:
            tokens = count(texts)
            print(
                f"bench: tokens max {max(tokens)}, mean"
                f" {statistics.mean(tokens):.0f}, at the limit"
                f" {sum(t >= 512 for t in tokens)} of {len(tokens)}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.embed")
    parser.add_argument("command", choices=["reembed", "bench"])
    parser.add_argument("embedder", nargs="?", default="fake")
    args = parser.parse_args(argv)
    with connect(settings().dsn) as conn:
        if args.command == "bench":
            rows = conn.execute("SELECT text FROM chunks").fetchall()
            bench([str(r[0]) for r in rows])
            return 0
        embedder = get(args.embedder)
        count = reembed(conn, embedder)
    print(f"re-embedded {count} chunks with {model_id(embedder)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
