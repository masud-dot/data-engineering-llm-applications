"""Chunk stage: pack paragraphs into size-limited chunks."""

from __future__ import annotations

import re

from llmdata.db import connect
from llmdata.pipeline.context import Context


def _pieces(text: str, size: int) -> list[str]:
    pieces: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(para.split())
        while len(para) > size:
            cut = para.rfind(" ", 0, size)
            cut = cut if cut > 0 else size
            pieces.append(para[:cut])
            para = para[cut:].strip()
        if para:
            pieces.append(para)
    return pieces


def split(
    text: str, size: int = 900, overlap: int = 120
) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece in _pieces(text, size - overlap):
        if current and len(current) + len(piece) + 1 > size:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            tail = tail[tail.find(" ") + 1 :] if " " in tail else ""
            current = f"{tail} {piece}".strip()
        else:
            current = f"{current} {piece}".strip()
    if current:
        chunks.append(current)
    return chunks


def run(ctx: Context) -> None:
    size = int(ctx.params.get("size", 900))
    overlap = int(ctx.params.get("overlap", 120))
    total = 0
    with connect(ctx.settings.dsn) as conn:
        conn.execute(
            "DELETE FROM staged_chunks WHERE run_id = %s",
            (ctx.run_id,),
        )
        rows = conn.execute(
            "SELECT doc_key, cleaned FROM staged"
            " WHERE run_id = %s AND op = 'upsert' ORDER BY doc_key",
            (ctx.run_id,),
        ).fetchall()
        for key, cleaned in rows:
            for ordinal, text in enumerate(
                split(cleaned or "", size, overlap)
            ):
                conn.execute(
                    "INSERT INTO staged_chunks"
                    " (run_id, doc_key, ordinal, text)"
                    " VALUES (%s, %s, %s, %s)",
                    (ctx.run_id, key, ordinal, text),
                )
                total += 1
    print(f"{total} chunks from {len(rows)} documents")
