"""A paused trigger DAG for each schedule in the policy files."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from airflow.providers.standard.operators.trigger_dagrun import (
    TriggerDagRunOperator,
)
from airflow.sdk import DAG

from llmdata.pipeline import spec

ROOT = Path(os.environ.get("LLMDATA_PIPELINES_DIR", "pipelines"))
UNTIL = os.environ.get("LLMDATA_UNTIL") or None


# region: schedules
def build(name: str, cron: str, conf: dict[str, object]) -> DAG:
    dag = DAG(
        f"schedule__{name}",
        schedule=cron,
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        catchup=False,  # one run catches up from the checkpoints
        max_active_runs=1,
        is_paused_upon_creation=True,
    )
    TriggerDagRunOperator(
        task_id="trigger", dag=dag, trigger_dag_id=name, conf=conf
    )
    return dag


for _name, _rule in spec.policy(ROOT, UNTIL).schedules.items():
    _dag = build(_name, _rule["cron"], dict(_rule.get("conf", {})))
    globals()[_dag.dag_id] = _dag
# endregion
