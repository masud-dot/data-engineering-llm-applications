"""--until chNN keeps only tests for Chapters 1 to NN."""

from __future__ import annotations

import pytest

from llmdata.pipeline.spec import chapter_no


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--until",
        default=None,
        help="run tests for chapters up to chNN",
    )
    parser.addoption(
        "--update-golden",
        action="store_true",
        help="rewrite golden files from this run's output",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    until = config.getoption("--until")
    if not until:
        return
    limit = chapter_no(str(until))
    keep: list[pytest.Item] = []
    drop: list[pytest.Item] = []
    for item in items:
        mark = item.get_closest_marker("chapter")
        (drop if mark and mark.args[0] > limit else keep).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep
