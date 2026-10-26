"""Freshness and deletion targets."""

from datetime import timedelta
from typing import get_args

import pytest

from llmdata.contracts import Origin, load_slas


@pytest.mark.chapter(2)
def test_every_source_has_targets() -> None:
    assert set(load_slas()) == set(get_args(Origin))


@pytest.mark.chapter(2)
def test_targets_are_tight_enough() -> None:
    for sla in load_slas().values():
        assert sla.max_lag <= timedelta(days=1)
        assert sla.delete_within <= timedelta(days=3)
    wordings = load_slas()["wordings"]
    assert wordings.delete_within <= timedelta(hours=4)
