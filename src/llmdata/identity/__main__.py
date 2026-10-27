"""Command line: trace a chunk ID back to its document and version."""

from __future__ import annotations

import argparse
import json

from llmdata.config import settings
from llmdata.db import connect
from llmdata.identity import trace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.identity")
    parser.add_argument("command", choices=["trace"])
    parser.add_argument("chunk_id")
    args = parser.parse_args(argv)
    cfg = settings()
    with connect(cfg.dsn) as conn:
        found = trace(conn, args.chunk_id, cfg.data_dir / "archive")
    print(json.dumps(found, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
