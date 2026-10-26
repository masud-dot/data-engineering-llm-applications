"""Embed stage: vectors for staged chunks."""

from __future__ import annotations

import os
from typing import Protocol

from llmdata.db import connect
from llmdata.embed.fake import FakeEmbedder, Vector
from llmdata.pipeline.context import Context


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[Vector]: ...


def get(name: str) -> Embedder:
    if name == "local":
        from llmdata.embed.local import LocalEmbedder

        return LocalEmbedder()
    return FakeEmbedder()


def run(ctx: Context) -> None:
    name = str(
        ctx.conf.get("embedder")
        or os.environ.get("EMBEDDER")
        or ctx.params.get("embedder", "fake")
    )
    embedder = get(name)
    batch = int(ctx.params.get("batch", 64))
    with connect(ctx.settings.dsn) as conn:
        rows = conn.execute(
            "SELECT doc_key, ordinal, text FROM staged_chunks"
            " WHERE run_id = %s AND embedding IS NULL"
            " ORDER BY doc_key, ordinal",
            (ctx.run_id,),
        ).fetchall()
        for start in range(0, len(rows), batch):
            part = rows[start : start + batch]
            vectors = embedder.embed([r[2] for r in part])
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE staged_chunks SET embedding = %s,"
                    " embedding_model = %s WHERE run_id = %s"
                    " AND doc_key = %s AND ordinal = %s",
                    [
                        (vec, embedder.name, ctx.run_id, key, ordinal)
                        for (key, ordinal, _), vec in zip(
                            part, vectors, strict=True
                        )
                    ],
                )
            conn.commit()
    print(f"embedded {len(rows)} chunks with {embedder.name}")
