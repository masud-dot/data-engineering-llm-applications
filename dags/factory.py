"""One Airflow DAG per directory under pipelines/."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

from llmdata.pipeline import spec

# region: dag-factory
ROOT = Path(os.environ.get("LLMDATA_PIPELINES_DIR", "pipelines"))
UNTIL = os.environ.get("LLMDATA_UNTIL") or None
PROFILE = os.environ.get("LLMDATA_PROFILE") or None
PYTHON = os.environ.get("LLMDATA_PYTHON", "/opt/venv/bin/python")
ENV = {
    "LLMDATA_RUN_ID": "{{ run_id }}",
    "LLMDATA_TRY": "{{ ti.try_number }}",
    "LLMDATA_CONF": "{{ dag_run.conf | tojson }}",
}


def build(name: str) -> DAG:
    rules = spec.policy(ROOT, UNTIL)
    with DAG(
        dag_id=name,
        schedule=None,
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        catchup=False,
        max_active_runs=1,
        tags=["llmdata"],
    ) as dag:
        previous = None
        for stage in spec.load(ROOT, name, UNTIL, PROFILE):
            task = BashOperator(
                task_id=stage.name,
                bash_command=(
                    f"{PYTHON} -m llmdata.pipeline"
                    f" stage {name} {stage.name}"
                ),
                env=ENV,
                append_env=True,
                retries=rules.retries,
                retry_delay=timedelta(seconds=rules.retry_delay_s),
                execution_timeout=timedelta(seconds=rules.timeout_s),
            )
            if previous is not None:
                previous >> task
            previous = task
    return dag


for _name in spec.pipelines(ROOT):
    globals()[_name] = build(_name)
# endregion
