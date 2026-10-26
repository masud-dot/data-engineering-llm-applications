"""Trigger a DAG run (or attach to one) and wait for its result."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time

import psycopg
from airflow_wait import COMPOSE


def state(dag: str, run_id: str) -> str | None:
    dsn = os.environ.get("LLMDATA_AIRFLOW_DSN", "dbname=airflow")
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT state FROM dag_run"
            " WHERE dag_id = %s AND run_id = %s",
            (dag, run_id),
        ).fetchone()
    return str(row[0]) if row else None


def wait(dag: str, run_id: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = state(dag, run_id)
        if current in ("success", "failed"):
            print(f"{dag} {run_id}: {current}", flush=True)
            return current == "success"
        time.sleep(5)
    print(f"{dag} {run_id}: still running after {timeout:.0f}s")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dag")
    parser.add_argument("--conf", default="{}")
    parser.add_argument("--attach", metavar="RUN_ID")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args()
    run_id = args.attach
    if not run_id:
        json.loads(args.conf)
        run_id = time.strftime(f"manual__{args.dag}__%Y%m%dT%H%M%S")
        subprocess.run(
            [
                *COMPOSE,
                "exec",
                "-T",
                "airflow",
                "airflow",
                "dags",
                "trigger",
                args.dag,
                "--run-id",
                run_id,
                "--conf",
                args.conf,
            ],
            check=True,
            capture_output=True,
        )
    print(f"RUN_ID={run_id}", flush=True)
    if args.no_wait:
        return 0
    return 0 if wait(args.dag, run_id, args.timeout) else 1


if __name__ == "__main__":
    raise SystemExit(main())
