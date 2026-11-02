"""Plans match what the pipeline builds; the bench times searches."""

from __future__ import annotations

import tomllib

import pytest

from llmdata.config import Settings
from llmdata.cost import PRICES as PRICE_FILE
from llmdata.cost import bench, measure, monthly, plan
from llmdata.db import connect
from llmdata.embed import get
from llmdata.pipeline.__main__ import main as pipeline


@pytest.fixture
def indexed(
    landed: Settings, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    monkeypatch.setenv("LLMDATA_DATA_DIR", str(landed.data_dir))
    for name in ("documents", "eval_sets"):
        assert pipeline(["run", name, "--run-id", f"{name}-0"]) == 0
    return landed


# region: cost-tests
@pytest.mark.chapter(19)
def test_a_plan_at_the_current_size_is_the_index(
    indexed: Settings,
) -> None:
    with connect(indexed.dsn) as conn:
        now, same = measure(conn), plan(conn, 900)
        smaller = plan(conn, 500)
    assert (same.chunks, same.chars) == (now.chunks, now.chars)
    assert smaller.chunks > now.chunks
    prices = tomllib.loads(PRICE_FILE.read_text())
    cheaper = monthly(smaller, prices, k=5)["prompts"]
    assert cheaper < monthly(now, prices, k=5)["prompts"]


@pytest.mark.chapter(19)
def test_the_bench_times_every_question(indexed: Settings) -> None:
    with connect(indexed.dsn) as conn:
        result = bench(conn, get("fake"), n=10)
    assert result["questions"] == 10
    assert 0 < result["p50_ms"] <= result["p95_ms"]


# endregion
