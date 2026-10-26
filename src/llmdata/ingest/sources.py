"""Change sources. SnapshotSource compares everything every run."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from psycopg.rows import dict_row

from llmdata.contracts import (
    ClaimRecord,
    Kind,
    Origin,
    SourceItem,
    require,
)
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


# region: landing-manifest
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


# endregion


def file_item(
    key: str, entry: tuple[str, str, str, Any]
) -> SourceItem:
    digest, ref, origin, meta = entry
    return SourceItem(
        doc_key=key,
        op="upsert",
        origin=cast(Origin, origin),
        kind=KINDS[origin],
        content_hash=digest,
        ref=ref,
        meta=meta,
    )


# region: claims-connector
def claim_item(record: ClaimRecord) -> SourceItem:
    return SourceItem(
        doc_key=f"claim:{record.claim_id}",
        op="delete" if record.deleted_at else "upsert",
        origin="claims",
        kind="record",
        content_hash=sha256(record.note.encode()),
        raw=record.note,
        meta={"region": record.region, "roles": ROLES["claims"]},
    )


def claim_rows(
    dsn: str, since: datetime | None = None, live_only: bool = False
) -> list[ClaimRecord]:
    """Claims changed since a point, checked against the contract."""
    sql = (
        "SELECT * FROM claims WHERE (%(s)s::timestamptz IS NULL"
        " OR updated_at > %(s)s::timestamptz)"
    )
    if live_only:
        sql += " AND deleted_at IS NULL"
    with connect(dsn, vectors=False) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql + " ORDER BY claim_id", {"s": since})
            return require(ClaimRecord, cur.fetchall(), "claim_id")


# endregion


def versions(conn: Conn) -> dict[str, str]:
    rows = conn.execute("SELECT doc_key, version FROM documents")
    return {str(k): str(v) for k, v in rows}


# region: snapshot-source
class SnapshotSource:
    """Stages every document whose content differs from the index."""

    def __init__(self) -> None:
        self._pending: Pending = {}

    def changes(
        self, ctx: Context, conn: Conn
    ) -> Iterator[SourceItem]:
        known = versions(conn)
        manifest = file_manifest(ctx.settings.data_dir)
        for key, entry in manifest.items():
            if known.get(key) != entry[0][:16]:
                yield file_item(key, entry)
        files = {key: entry[0] for key, entry in manifest.items()}
        self._pending["files"] = (None, files)
        rows = claim_rows(ctx.settings.source_dsn, live_only=True)
        for record in rows:
            item = claim_item(record)
            if known.get(item.doc_key) != item.content_hash[:16]:
                yield item

    def pending(self) -> Pending:
        return self._pending


# endregion
