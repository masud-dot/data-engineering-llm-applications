"""Embed stage on Spark: the same vectors, one model per partition."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Iterator
from functools import partial

import numpy as np

from llmdata.db import connect
from llmdata.embed import TODO, UPDATE, choose, get, guard, model_id
from llmdata.pipeline.context import Context

Row = tuple[str, int, str]
Out = tuple[str, int, list[float]]


# region: spark-embed
def embed_partition(name: str, rows: Iterable[Row]) -> Iterator[Out]:
    """Runs on a worker: load the model once, embed in batches."""
    embedder, part = get(name), list(rows)
    for start in range(0, len(part), 64):
        some = part[start : start + 64]
        vectors = embedder.embed([text for _, _, text in some])
        for (key, ordinal, _), vec in zip(some, vectors, strict=True):
            yield key, ordinal, [float(x) for x in vec]


def on_spark(
    rows: list[Row], name: str, master: str, n: int
) -> list[Out]:
    """The distributed part: rows in, vectors out."""
    from pyspark.sql import SparkSession  # only in the spark profile

    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    spark = SparkSession.builder.master(master).getOrCreate()
    try:
        job = spark.sparkContext.parallelize(rows, n)
        return job.mapPartitions(
            partial(embed_partition, name)
        ).collect()
    finally:
        spark.stop()


# endregion


def run(ctx: Context) -> None:
    name = choose(ctx)
    model = model_id(get(name))
    master = str(ctx.params.get("master", "local[*]"))
    slices = int(ctx.params.get("partitions", 8))
    with connect(ctx.settings.dsn) as conn:
        guard(conn, model)
        todo = conn.execute(TODO, (ctx.run_id,)).fetchall()
        rows = [
            (key, ordinal, text) for key, ordinal, text, _ in todo
        ]
        out = on_spark(rows, name, master, slices)
        values = [
            (np.asarray(v, dtype=np.float32), model, ctx.run_id, k, o)
            for k, o, v in out
        ]
        with conn.cursor() as cur:
            cur.executemany(UPDATE, values)
    print(f"embedded {len(out)} chunks with {model} on Spark")
