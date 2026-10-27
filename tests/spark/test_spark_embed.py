"""The Spark job gives the same vectors as the in-process stage."""

from __future__ import annotations

import os
import shutil
import sys
from functools import partial

import numpy as np
import pytest

from llmdata.embed.fake import FakeEmbedder
from llmdata.embed.spark import embed_partition

pytest.importorskip("pyspark")
if shutil.which("java") is None:
    pytest.skip("Spark needs Java", allow_module_level=True)


@pytest.mark.chapter(9)
def test_spark_partitions_match_in_process_vectors() -> None:
    from pyspark.sql import SparkSession

    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    rows = [
        (f"doc-{i}", 0, f"Claim {i} for escape of water")
        for i in range(50)
    ]
    spark = SparkSession.builder.master("local[2]").getOrCreate()
    try:
        job = spark.sparkContext.parallelize(rows, 4)
        out = job.mapPartitions(
            partial(embed_partition, "fake")
        ).collect()
    finally:
        spark.stop()
    want = FakeEmbedder().embed([text for _, _, text in rows])
    got = {(key, ordinal): vec for key, ordinal, vec in out}
    assert len(got) == len(rows)
    for (key, ordinal, _), vec in zip(rows, want, strict=True):
        assert np.allclose(got[(key, ordinal)], vec)
