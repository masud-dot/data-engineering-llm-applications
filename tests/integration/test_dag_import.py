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
    assert len(found["documents"].task_ids) == 14


@pytest.mark.chapter(12)
def test_schedules_trigger_paused_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("airflow.sdk")
    from airflow.sdk import DAG

    monkeypatch.setenv("LLMDATA_PIPELINES_DIR", "pipelines")
    monkeypatch.setenv("LLMDATA_UNTIL", "ch20")
    found = {
        value.dag_id: value
        for value in runpy.run_path("dags/schedules.py").values()
        if isinstance(value, DAG)
    }
    assert list(found) == ["schedule__documents"]
    dag = found["schedule__documents"]
    assert dag.is_paused_upon_creation and not dag.catchup
