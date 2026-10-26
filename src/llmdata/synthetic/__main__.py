"""make data: build day 0, or apply change set DAY=N."""

from __future__ import annotations

import argparse
import os

from llmdata.config import settings
from llmdata.synthetic import (
    RECORD,
    SCALES,
    apply_changes,
    corpus_hash,
    load_claims,
    parse_changes,
    plan,
    recorded,
    write_files,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.synthetic")
    parser.add_argument("--day", type=int, default=0)
    parser.add_argument("--changes", default="update:5,soft:2,hard:1")
    parser.add_argument(
        "--scale",
        choices=sorted(SCALES),
        default=os.environ.get("LLMDATA_CORPUS", "full"),
    )
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--hash-only", action="store_true")
    parser.add_argument("--files-only", action="store_true")
    args = parser.parse_args(argv)
    cfg = settings()
    if args.day:
        done = apply_changes(
            cfg.source_dsn,
            cfg.data_dir,
            args.day,
            parse_changes(args.changes),
        )
        print(f"day {args.day}: {done or 'already applied'}")
        return 0
    if args.record:
        lines = ["# Logical corpus hashes, by scale.", "[hash]"]
        lines += [f'{s} = "{corpus_hash(plan(s))}"' for s in SCALES]
        RECORD.write_text("\n".join(lines) + "\n")
        print(f"recorded {RECORD}")
        return 0
    corpus = plan(args.scale)
    digest = corpus_hash(corpus)
    if digest != recorded(args.scale):
        print(f"corpus hash {digest} does not match {RECORD}")
        return 1
    print(f"corpus {args.scale} {digest[:16]} matches the record")
    if args.hash_only:
        return 0
    write_files(corpus, cfg.data_dir)
    if args.files_only:
        print("files written; source database untouched")
        return 0
    load_claims(cfg.source_dsn, corpus["claims"])
    print("day 0 written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
