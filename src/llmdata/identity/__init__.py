"""Identity stage: stable IDs, versions and a record of each."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from llmdata.db import Conn, connect
from llmdata.pipeline.context import Context

# region: identity-sql
IDENTIFY = (  # IDs come from keys, versions from content
    "UPDATE staged SET doc_id = left(encode(sha256(convert_to("
    "origin || '|' || doc_key, 'UTF8')), 'hex'), 16),"
    " version = left(content_hash, 16)"
    " WHERE run_id = %s AND op = 'upsert'"
)
NUMBER = (  # a chunk's ID: document ID, version and ordinal
    "UPDATE staged_chunks c SET chunk_id = s.doc_id || ':'"
    " || s.version || ':' || lpad(c.ordinal::text, 4, '0')"
    " FROM staged s WHERE s.run_id = c.run_id"
    " AND s.doc_key = c.doc_key AND c.run_id = %s"
)
RECORD = (  # first sight of each version; later runs change nothing
    "INSERT INTO versions (doc_id, version, doc_key, origin,"
    " content_hash, ref, meta, first_run)"
    " SELECT doc_id, version, doc_key, origin, content_hash, ref,"
    " meta - 'minhash', run_id FROM staged"
    " WHERE run_id = %s AND op = 'upsert' ON CONFLICT DO NOTHING"
)
# endregion


# region: archive
def keep(archive: Path, digest: str, data: bytes) -> Path:
    """Store bytes once, under their own SHA-256, checked first."""
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError(
            f"content changed after ingestion: {digest}"
        )
    path = archive / digest[:2] / digest
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(f".{digest}.part")
        part.write_bytes(data)
        os.replace(part, path)  # appears only when complete
    return path


def run(ctx: Context) -> None:
    landing = ctx.settings.data_dir / "landing"
    archive = ctx.settings.data_dir / "archive"
    with connect(ctx.settings.dsn) as conn:
        conn.execute(IDENTIFY, (ctx.run_id,))
        chunks = conn.execute(NUMBER, (ctx.run_id,)).rowcount
        items = conn.execute(
            "SELECT content_hash, ref, raw FROM staged"
            " WHERE run_id = %s AND op = 'upsert'",
            (ctx.run_id,),
        ).fetchall()
        for digest, ref, raw in items:
            if ref:
                keep(archive, digest, (landing / ref).read_bytes())
            else:
                keep(archive, digest, str(raw or "").encode())
        new = conn.execute(RECORD, (ctx.run_id,)).rowcount
    print(f"identified {chunks} chunks; {new} new versions recorded")


# endregion


# region: trace
TRACE = (
    "SELECT v.doc_key, v.content_hash, v.ref, v.meta ->> 'edition',"
    " v.first_run, d.version FROM versions v"
    " LEFT JOIN documents d USING (doc_id)"
    " WHERE v.doc_id = %s AND v.version = %s"
)


def trace(conn: Conn, chunk_id: str, archive: Path) -> dict[str, Any]:
    """Where a chunk came from: document, version, bytes and run."""
    doc_id, version, _ = chunk_id.split(":")
    row = conn.execute(TRACE, (doc_id, version)).fetchone()
    if row is None:
        raise LookupError(f"no recorded version for {chunk_id}")
    key, digest, ref, edition, run, live = row
    return {
        "document": key,
        "version": version,
        "edition": edition,
        "landed_as": ref,
        "archived": str(archive / digest[:2] / digest),
        "first_run": run,
        "live_version": live,
        "current": live == version,
    }


# endregion
