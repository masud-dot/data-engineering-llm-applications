"""WatermarkSource: incremental changes, deletes included."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from llmdata.contracts import SourceItem
from llmdata.db import Conn
from llmdata.ingest.sources import (
    KINDS,
    Pending,
    claim_item,
    claim_rows,
    file_item,
    file_manifest,
    versions,
)
from llmdata.pipeline.context import Context

OVERLAP = timedelta(minutes=5)


class WatermarkSource:
    def __init__(self) -> None:
        self._pending: Pending = {}

    def changes(
        self, ctx: Context, conn: Conn
    ) -> Iterator[SourceItem]:
        marks = {
            str(name): (mark, dict(manifest or {}))
            for name, mark, manifest in conn.execute(
                "SELECT source, watermark, manifest FROM checkpoints"
            )
        }
        known = versions(conn)
        current = file_manifest(ctx.settings.data_dir)
        before = marks.get("files", (None, {}))[1]
        for key, entry in current.items():
            digest = entry[0]
            if (
                before.get(key) != digest
                and known.get(key) != digest[:16]
            ):
                yield file_item(key, entry)
        for key in sorted(set(before) - set(current)):
            if key in known:
                origin = key.split(":", 1)[1].split("/", 1)[0]
                yield SourceItem(
                    doc_key=key,
                    op="delete",
                    origin=origin,
                    kind=KINDS[origin],
                )
        files = {key: entry[0] for key, entry in current.items()}
        self._pending["files"] = (None, files)
        mark: datetime | None = marks.get("claims", (None, {}))[0]
        since = mark - OVERLAP if mark else None
        top = mark
        rows = claim_rows(ctx.settings.source_dsn, since)
        for record in rows:
            updated = record.updated_at
            top = max(top, updated) if top else updated
            item = claim_item(record)
            if item.op == "delete":
                if item.doc_key in known:
                    yield item
            elif known.get(item.doc_key) != item.content_hash[:16]:
                yield item
        self._pending["claims"] = (top, {})

    def pending(self) -> Pending:
        return self._pending
