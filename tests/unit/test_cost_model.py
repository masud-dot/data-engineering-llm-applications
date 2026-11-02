"""The cost model's arithmetic, on numbers small enough to check."""

from __future__ import annotations

import pytest

from llmdata.cost import Facts, monthly, reembed

PRICES = {
    "chars_per_token": 4.0,
    "storage_gb_month": 1.0,
    "per_million_tokens": {
        "embedding": 1.0,
        "prompt": 2.0,
        "answer": 4.0,
    },
    "usage": {
        "documents": 20,
        "queries": 1_000_000,
        "answer_tokens": 1,
        "changed_share": 0.5,
    },
}


@pytest.mark.chapter(19)
def test_costs_scale_from_the_index_to_production() -> None:
    f = Facts(
        documents=10, chunks=25_000, chars=4_000_000, bytes=10**9
    )
    cost = monthly(f, PRICES, k=2)
    assert cost == {  # 2M tokens at production volume, 40 a chunk
        "embedding": 1.0,  # half of them re-embedded, 1 a million
        "storage": 2.0,  # 2 GB at 1 a GB-month
        "prompts": 160.0,  # 1M questions, 2 chunks of 40 tokens
        "answers": 4.0,
    }
    assert reembed(f, PRICES) == 2.0
