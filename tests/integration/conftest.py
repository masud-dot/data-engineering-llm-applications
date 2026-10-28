from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from llmdata.config import Settings, settings
from llmdata.db import migrate, reset
from llmdata.synthetic import load_claims, plan, write_files


# region: test-databases
@pytest.fixture(scope="session")
def pg(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Settings]:
    base = os.environ.get("LLMDATA_DSN", "dbname=llmdata")

    def db(name: str) -> str:
        return make_conninfo(base, dbname=name)

    try:
        psycopg.connect(db("postgres"), connect_timeout=3).close()
    except psycopg.OperationalError:
        if os.environ.get("LLMDATA_REQUIRE_DB") == "1":
            raise  # CI and the spike: a missing database fails
        pytest.skip("Postgres is not reachable")
    with psycopg.connect(db("postgres"), autocommit=True) as conn:
        for name in ("llmdata_test", "source_test"):
            conn.execute(
                f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"
            )
            conn.execute(f"CREATE DATABASE {name}")
    migrate(db("llmdata_test"), Path("deploy/sql/migrations"))
    patch = pytest.MonkeyPatch()
    for key, value in {
        "LLMDATA_DSN": db("llmdata_test"),
        "LLMDATA_SOURCE_DSN": db("source_test"),
        "LLMDATA_DATA_DIR": str(tmp_path_factory.mktemp("data")),
        "LLMDATA_PIPELINES_DIR": "pipelines",
        "LLMDATA_UNTIL": "ch20",
        "EMBEDDER": "fake",
    }.items():
        patch.setenv(key, value)
    yield settings()
    patch.undo()


# endregion


@pytest.fixture
def landed(pg: Settings, tmp_path: Path) -> Settings:
    """The small day-0 corpus in a fresh landing zone; empty index."""
    reset(pg.dsn)
    corpus = plan("small")
    write_files(corpus, tmp_path)
    load_claims(pg.source_dsn, corpus["claims"])
    return replace(pg, data_dir=tmp_path)
