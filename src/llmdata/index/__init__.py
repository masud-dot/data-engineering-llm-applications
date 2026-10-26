"""Index stage and index fingerprint."""

from __future__ import annotations

import hashlib

import numpy as np

from llmdata.db import Conn
from llmdata.loader import load_object
from llmdata.pipeline.context import Context

DEFAULT = "llmdata.index.writers:DirectWriter"


def run(ctx: Context) -> None:
    writer = load_object(ctx.params.get("writer", DEFAULT))()
    count = writer(ctx)
    print(f"index writer {type(writer).__name__}: {count} documents")


def index_hash(conn: Conn) -> tuple[str, int]:
    digest = hashlib.sha256()
    rows = conn.execute(
        "SELECT chunk_id, text, embedding FROM chunks"
        " ORDER BY chunk_id"
    ).fetchall()
    for chunk_id, text, vec in rows:
        digest.update(chunk_id.encode())
        digest.update(text.encode())
        values = vec.to_numpy() if hasattr(vec, "to_numpy") else vec
        digest.update(np.asarray(values, dtype=np.float32).tobytes())
    return digest.hexdigest(), len(rows)
