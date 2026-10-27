"""Database connections and numbered migrations."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from llmdata.config import settings

Conn = psycopg.Connection[tuple[Any, ...]]
MIGRATIONS = Path(
    os.environ.get("LLMDATA_MIGRATIONS_DIR", "deploy/sql/migrations")
)


def connect(dsn: str, vectors: bool = True) -> Conn:
    conn = psycopg.connect(dsn)
    if vectors:
        register_vector(conn)
    return conn


def migrate(dsn: str, folder: Path = MIGRATIONS) -> list[str]:
    applied: list[str] = []
    with connect(dsn, vectors=False) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations"
            " (name text PRIMARY KEY,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM schema_migrations"
            )
        }
        for path in sorted(folder.glob("*.sql")):
            if path.name in done:
                continue
            conn.execute(path.read_text())
            conn.execute(
                "INSERT INTO schema_migrations (name) VALUES (%s)",
                (path.name,),
            )
            applied.append(path.name)
    return applied


PIPELINE_TABLES = (
    "chunks, documents, staged_chunks, staged, tombstones,"
    " pending_checkpoints, checkpoints, ledger, versions,"
    " embedding_cache"
)


def reset(dsn: str) -> None:
    with connect(dsn) as conn:
        conn.execute(f"TRUNCATE {PIPELINE_TABLES} CASCADE")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.db")
    parser.add_argument("command", choices=["migrate", "reset"])
    args = parser.parse_args(argv)
    dsn = settings().dsn
    if args.command == "migrate":
        names = migrate(dsn)
        print("applied:", ", ".join(names) or "none")
    else:
        reset(dsn)
        print("pipeline tables emptied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
