"""Wait until Airflow lists every pipeline as a DAG."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
from llmdata.pipeline.spec import load, pipelines  # noqa: E402

COMPOSE = [
    "docker",
    "compose",
    "-p",
    "llmdata",
    "-f",
    "deploy/compose/core.yml",
    "--env-file",
    "deploy/compose/images.env",
    "--env-file",
    "deploy/compose/.env",
]


def dag_ids() -> set[str]:
    done = subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "airflow",
            "airflow",
            "dags",
            "list",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    start = done.stdout.find("[")
    if done.returncode or start < 0:
        return set()
    try:
        return {
            str(d["dag_id"]) for d in json.loads(done.stdout[start:])
        }
    except (ValueError, KeyError, TypeError):
        return set()


def main(timeout: float = 900) -> int:
    root, until = Path("pipelines"), os.environ.get("UNTIL")
    want = {p for p in pipelines(root) if load(root, p, until)}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        have = dag_ids()
        if want <= have:
            print("airflow ready:", ", ".join(sorted(have)))
            return 0
        time.sleep(5)
    print(
        "airflow did not list every pipeline in time", file=sys.stderr
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
