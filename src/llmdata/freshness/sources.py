"""WatermarkSource: incremental changes, deletes included."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from itertools import chain
from typing import Any, cast

from llmdata.contracts import Origin, SourceItem
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
MAX_REMOVED = 0.2
Marks = dict[str, tuple[Any, dict[str, Any]]]


class SourceGone(RuntimeError):
    """A source lost more of its keys than one run may delete."""


def guard(name: str, before: int, gone: int, limit: float) -> None:
    """Refuse a run that would delete too much of one source."""
    if before and gone > before * limit:
        raise SourceGone(
            f"{name}: {gone} of {before} documents gone;"
            f" refusing to delete more than {limit:.0%}"
        )


def limit(ctx: Context) -> float:
    value = ctx.conf.get("max_removed")
    if value is None:
        value = ctx.params.get("max_removed", MAX_REMOVED)
    return float(value)


def erased(conn: Conn) -> set[str]:
    rows = conn.execute(
        "SELECT doc_key FROM tombstones WHERE reason = 'erased'"
    )
    return {str(row[0]) for row in rows}


class WatermarkSource:
    def __init__(self) -> None:
        self._pending: Pending = {}

    def changes(
        self, ctx: Context, conn: Conn
    ) -> Iterator[SourceItem]:
        marks: Marks = {
            str(name): (mark, dict(manifest or {}))
            for name, mark, manifest in conn.execute(
                "SELECT source, watermark, manifest FROM checkpoints"
            )
        }
        known, gone = versions(conn), erased(conn)
        skipped = 0
        for item in chain(
            self.files(ctx, marks, known),
            self.claims(ctx, marks, known),
        ):
            if item.doc_key in gone and item.op == "upsert":
                skipped += 1  # erased, yet the source still has it
                continue
            yield item
        if skipped:
            print(f"skipped {skipped} erased documents at source")

    def files(
        self, ctx: Context, marks: Marks, known: dict[str, str]
    ) -> Iterator[SourceItem]:
        current = file_manifest(ctx.settings.data_dir)
        before = marks.get("files", (None, {}))[1]
        # region: manifest-diff
        removed = sorted(set(before) - set(current))
        guard("landing zone", len(before), len(removed), limit(ctx))
        for key, entry in current.items():
            digest = entry[0]
            if (
                before.get(key) != digest
                and known.get(key) != digest[:16]
            ):
                yield file_item(key, entry)
        for key in removed:
            if key in known:
                origin = cast(Origin, key[5:].split("/", 1)[0])
                yield SourceItem(
                    doc_key=key,
                    op="delete",
                    origin=origin,
                    kind=KINDS[origin],
                )
        # endregion
        files = {key: entry[0] for key, entry in current.items()}
        self._pending["files"] = (None, files)

    def claims(
        self, ctx: Context, marks: Marks, known: dict[str, str]
    ) -> Iterator[SourceItem]:
        # region: claims-watermark
        mark: datetime | None = marks.get("claims", (None, {}))[0]
        since = mark - OVERLAP if mark else None
        top = mark
        for record in claim_rows(ctx.settings.source_dsn, since):
            updated = record.updated_at
            top = max(top, updated) if top else updated
            item = claim_item(record)
            if item.op == "delete":
                if item.doc_key in known:
                    yield item
            elif known.get(item.doc_key) != item.content_hash[:16]:
                yield item
        self._pending["claims"] = (top, {})
        # endregion

    def pending(self) -> Pending:
        return self._pending
