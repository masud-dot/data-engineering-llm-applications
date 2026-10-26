"""Chapter 1's first smoke test: the stack is up and reachable."""

import os

import psycopg
import pytest

from llmdata.config import settings
from llmdata.pipeline.__main__ import main as pipeline


# region: smoke-test
def reachable(dsn: str) -> bool:
    try:
        with psycopg.connect(dsn, connect_timeout=3):
            return True
    except psycopg.OperationalError:
        return False


@pytest.fixture
def stack() -> None:
    if not reachable(settings().dsn):
        if os.environ.get("LLMDATA_REQUIRE_DB") == "1":
            pytest.fail("the stack is not running: run make up")
        pytest.skip("the stack is not running: run make up")


@pytest.mark.chapter(1)
@pytest.mark.usefixtures("stack")
def test_both_databases_answer() -> None:
    cfg = settings()
    with psycopg.connect(cfg.dsn) as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
    assert row is not None, "pgvector is missing"
    assert reachable(cfg.source_dsn)


@pytest.mark.chapter(1)
@pytest.mark.usefixtures("stack")
def test_skeleton_pipeline_runs() -> None:
    assert pipeline(["stage", "documents", "00-smoke"]) == 0


# endregion
