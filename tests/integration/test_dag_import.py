import runpy

import pytest


@pytest.mark.chapter(3)
def test_factory_builds_one_dag_per_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("airflow.sdk")
    from airflow.sdk import DAG

    monkeypatch.setenv("LLMDATA_PIPELINES_DIR", "pipelines")
    monkeypatch.setenv("LLMDATA_UNTIL", "ch20")
    found = {
        name: value
        for name, value in runpy.run_path("dags/factory.py").items()
        if isinstance(value, DAG)
    }
    assert set(found) == {"documents", "retry_demo"}
    assert found["documents"].task_ids[0] == "00-smoke"
    assert len(found["documents"].task_ids) == 13
