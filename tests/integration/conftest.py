from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from llmdata.config import Settings, settings
from llmdata.db import migrate


@pytest.fixture(scope="session")
def pg(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Settings]:
    base = os.environ.get(
        "LLMDATA_DSN", "postgresql://llmdata@localhost:55432/llmdata"
    )
    root = base.rsplit("/", 1)[0]
    try:
        psycopg.connect(root + "/postgres", connect_timeout=3).close()
    except psycopg.OperationalError:
        if os.environ.get("LLMDATA_REQUIRE_DB") == "1":
            raise
        pytest.skip("Postgres is not reachable")
    with psycopg.connect(root + "/postgres", autocommit=True) as conn:
        for name in ("llmdata_test", "source_test"):
            conn.execute(
                f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"
            )
            conn.execute(f"CREATE DATABASE {name}")
    migrate(root + "/llmdata_test", Path("deploy/sql/migrations"))
    patch = pytest.MonkeyPatch()
    for key, value in {
        "LLMDATA_DSN": root + "/llmdata_test",
        "LLMDATA_SOURCE_DSN": root + "/source_test",
        "LLMDATA_DATA_DIR": str(tmp_path_factory.mktemp("data")),
        "LLMDATA_PIPELINES_DIR": "pipelines",
        "LLMDATA_UNTIL": "ch20",
        "EMBEDDER": "fake",
    }.items():
        patch.setenv(key, value)
    yield settings()
    patch.undo()
