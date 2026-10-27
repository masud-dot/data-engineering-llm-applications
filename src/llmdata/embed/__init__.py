"""Embed stage: vectors for staged chunks, one model per index."""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from typing import Protocol

import numpy as np

from llmdata.db import Conn, connect
from llmdata.embed.fake import FakeEmbedder, Vector
from llmdata.pipeline.context import Context


# region: embedder
class Embedder(Protocol):
    name: str  # the model
    revision: str  # anything else that changes its vectors
    languages: frozenset[str]  # what it was trained on; empty: any

    def embed(self, texts: list[str]) -> list[Vector]: ...


def model_id(embedder: Embedder) -> str:
    """Stored with every vector: equal IDs mean comparable vectors."""
    return f"{embedder.name}@{embedder.revision}"


def get(name: str) -> Embedder:
    if name == "local":
        from llmdata.embed.local import LocalEmbedder

        return LocalEmbedder()
    return FakeEmbedder()


def choose(ctx: Context) -> str:
    """Run configuration, then environment, then the stage file."""
    return str(
        ctx.conf.get("embedder")
        or os.environ.get("EMBEDDER")
        or ctx.params.get("embedder", "fake")
    )


# endregion


# region: embed-cache
REMEMBER = (
    "INSERT INTO embedding_cache (model, text_hash, embedding)"
    " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
)


def cached(
    conn: Conn, embedder: Embedder, model: str, texts: list[str]
) -> tuple[list[Vector], int]:
    """Vectors for texts, computing only the ones not seen before."""
    keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
    found = {
        str(k): np.asarray(v.to_numpy(), dtype=np.float32)
        for k, v in conn.execute(
            "SELECT text_hash, embedding FROM embedding_cache"
            " WHERE model = %s AND text_hash = ANY(%s)",
            (model, keys),
        )
    }
    hits = sum(k in found for k in keys)
    todo = [i for i, k in enumerate(keys) if k not in found]
    if todo:
        fresh = embedder.embed([texts[i] for i in todo])
        rows = [
            (model, keys[i], v)
            for i, v in zip(todo, fresh, strict=True)
        ]
        with conn.cursor() as cur:
            cur.executemany(REMEMBER, rows)
        found.update({key: vec for _, key, vec in rows})
    return [found[k] for k in keys], hits


# endregion


TODO = (
    "SELECT c.doc_key, c.ordinal, c.text, s.meta ->> 'language'"
    " FROM staged_chunks c JOIN staged s USING (run_id, doc_key)"
    " WHERE c.run_id = %s AND c.embedding IS NULL ORDER BY 1, 2"
)
UPDATE = (
    "UPDATE staged_chunks SET embedding = %s, embedding_model = %s"
    " WHERE run_id = %s AND doc_key = %s AND ordinal = %s"
)
LIVE = "SELECT DISTINCT embedding_model FROM chunks"


# region: model-guard
def guard(conn: Conn, model: str) -> None:
    """Refuse to add vectors from a model the index does not use."""
    live = {str(m) for (m,) in conn.execute(LIVE)}
    if live - {model}:
        raise RuntimeError(
            f"the index holds {sorted(live)}; embedding with {model}"
            " needs a re-embed of every chunk (make reembed)"
        )


# endregion


# region: embed-stage
def run(ctx: Context) -> None:
    embedder = get(choose(ctx))
    model = model_id(embedder)
    batch = int(ctx.params.get("batch", 64))
    known, other = embedder.languages, Counter[str]()
    done = hits = 0
    with connect(ctx.settings.dsn) as conn:
        guard(conn, model)
        rows = conn.execute(TODO, (ctx.run_id,)).fetchall()
        for start in range(0, len(rows), batch):
            part = rows[start : start + batch]
            texts = [text for _, _, text, _ in part]
            vectors, found = cached(conn, embedder, model, texts)
            pairs = zip(part, vectors, strict=True)
            values = [
                (vec, model, ctx.run_id, key, ordinal)
                for (key, ordinal, _, _), vec in pairs
            ]
            with conn.cursor() as cur:
                cur.executemany(UPDATE, values)
            conn.commit()  # a retry resumes after this batch
            done, hits = done + len(part), hits + found
            if known:  # count text the model was not trained on
                other.update(x[3] for x in part if x[3] not in known)
    print(
        f"embedded {done} chunks with {model}; {hits} from the cache"
    )
    if other:
        print(f"outside the model's languages: {dict(other)}")


# endregion


# region: reembed
def reembed(conn: Conn, embedder: Embedder, batch: int = 64) -> int:
    """Embed every published chunk again, then switch all at once."""
    model = model_id(embedder)
    conn.execute("LOCK TABLE chunks IN SHARE ROW EXCLUSIVE MODE")
    conn.execute(
        "CREATE TEMP TABLE fresh (chunk_id text PRIMARY KEY,"
        " embedding vector(384)) ON COMMIT DROP"
    )
    rows = conn.execute(
        "SELECT chunk_id, text FROM chunks"
    ).fetchall()
    for start in range(0, len(rows), batch):
        part = rows[start : start + batch]
        vectors, _ = cached(
            conn, embedder, model, [t for _, t in part]
        )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO fresh VALUES (%s, %s)",
                [
                    (c, v)
                    for (c, _), v in zip(part, vectors, strict=True)
                ],
            )
    conn.execute(
        "UPDATE chunks c SET embedding = f.embedding,"
        " embedding_model = %s FROM fresh f"
        " WHERE f.chunk_id = c.chunk_id",
        (model,),
    )
    return len(rows)


# endregion
