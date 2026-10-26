"""Change sources. SnapshotSource compares everything every run."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from llmdata.contracts import Kind, SourceItem
from llmdata.db import Conn, connect
from llmdata.pipeline.context import Context

KINDS: dict[str, Kind] = {
    "wordings": "pdf",
    "endorsements": "pdf",
    "guidelines": "html",
    "emails": "eml",
}
ROLES = {
    "wordings": ["agent", "underwriter", "claims"],
    "endorsements": ["underwriter"],
    "guidelines": ["underwriter"],
    "emails": ["claims"],
    "claims": ["claims"],
}
Manifest = dict[str, tuple[str, str, str, dict[str, Any]]]
Pending = dict[str, tuple[datetime | None, dict[str, str]]]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_manifest(data_dir: Path) -> Manifest:
    """doc_key -> (hash, ref, origin, meta) for every landed file."""
    landing = data_dir / "landing"
    found: Manifest = {}
    for path in sorted(landing.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(landing)
        origin, region = rel.parts[0], rel.parts[1]
        meta = {"region": region, "roles": ROLES[origin]}
        found[f"file:{rel.as_posix()}"] = (
            sha256(path.read_bytes()),
            rel.as_posix(),
            origin,
            meta,
        )
    return found


def file_item(
    key: str, entry: tuple[str, str, str, Any]
) -> SourceItem:
    digest, ref, origin, meta = entry
    return SourceItem(
        doc_key=key,
        op="upsert",
        origin=origin,
        kind=KINDS[origin],
        content_hash=digest,
        ref=ref,
        meta=meta,
    )


def claim_item(
    claim_id: str, region: str, note: str, op: str = "upsert"
) -> SourceItem:
    return SourceItem(
        doc_key=f"claim:{claim_id}",
        op="delete" if op == "delete" else "upsert",
        origin="claims",
        kind="record",
        content_hash=sha256(note.encode()),
        raw=note,
        meta={"region": region, "roles": ROLES["claims"]},
    )


def claim_rows(
    dsn: str, since: datetime | None = None, live_only: bool = False
) -> list[tuple[Any, ...]]:
    sql = (
        "SELECT claim_id, region, note, updated_at, deleted_at"
        " FROM claims WHERE (%(s)s::timestamptz IS NULL"
        " OR updated_at > %(s)s::timestamptz)"
    )
    if live_only:
        sql += " AND deleted_at IS NULL"
    with connect(dsn, vectors=False) as conn:
        return conn.execute(
            sql + " ORDER BY claim_id", {"s": since}
        ).fetchall()


def versions(conn: Conn) -> dict[str, str]:
    rows = conn.execute("SELECT doc_key, version FROM documents")
    return {str(k): str(v) for k, v in rows}


class SnapshotSource:
    """Stages every document whose content differs from the index."""

    def changes(
        self, ctx: Context, conn: Conn
    ) -> Iterator[SourceItem]:
        known = versions(conn)
        manifest = file_manifest(ctx.settings.data_dir)
        for key, entry in manifest.items():
            if known.get(key) != entry[0][:16]:
                yield file_item(key, entry)
        rows = claim_rows(ctx.settings.source_dsn, live_only=True)
        for claim_id, region, note, _, _ in rows:
            item = claim_item(claim_id, region, note)
            if known.get(item.doc_key) != item.content_hash[:16]:
                yield item

    def pending(self) -> Pending:
        return {}
