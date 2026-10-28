"""Spikes S-1, S-2, S-4 and S-5 in one run. Results go to spike/."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, TextIO

sys.path.insert(0, "src")
from llmdata.embed.fake import RECORDED_SAMPLE_HASH  # noqa: E402

OUT = Path("spike")
COMPOSE = ("docker compose -p llmdata -f deploy/compose/core.yml"
           " --env-file deploy/compose/images.env"
           " --env-file deploy/compose/.env")
AIRFLOW = f"{COMPOSE} exec -T airflow"
PSQL = f"{COMPOSE} exec -T postgres psql -U llmdata -At"
IMAGES = ["pgvector/pgvector:pg17",
          "apache/airflow:3.3.2-python3.12"]
PG_IMAGE = ("pgvector/pgvector:pg17@sha256:"
            "ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d")
GIB = 1024**3
UNITS = {"b": 1.0, "kb": 1e3, "mb": 1e6, "gb": 1e9, "kib": 1024.0,
         "mib": 1024.0**2, "gib": 1024.0**3}
results: dict[str, Any] = {"facts": {}, "checks": []}
LOG: list[TextIO] = []


def sh(cmd: str, check: bool = True) -> str:
    print(f"+ {cmd}", flush=True)
    done = subprocess.run(cmd, shell=True, text=True,
                          capture_output=True)
    LOG[0].write(f"+ {cmd}\n{done.stdout}{done.stderr}\n")
    LOG[0].flush()
    if check and done.returncode:
        tail = (done.stdout + done.stderr)[-1500:]
        raise RuntimeError(f"exit {done.returncode}: {cmd}\n{tail}")
    return done.stdout.strip()


def timed(cmd: str) -> float:
    start = time.monotonic()
    sh(cmd)
    return round(time.monotonic() - start, 1)


def record(spike: str, name: str, passed: bool, detail: object) -> None:
    results["checks"].append(
        {"spike": spike, "check": name, "pass": bool(passed),
         "detail": str(detail)})
    print("PASS" if passed else "FAIL", spike, name, detail, flush=True)


def to_bytes(text: str) -> float:
    match = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", text)
    if not match:
        return 0.0
    return float(match.group(1)) * UNITS.get(match.group(2).lower(), 1)


class MemWatch(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.peak = 0.0
        self.rows: list[tuple[int, float]] = []
        self.halt = threading.Event()

    def run(self) -> None:
        fmt = "'{{.Name}}\t{{.MemUsage}}'"
        while not self.halt.is_set():
            out = subprocess.run(
                f"docker stats --no-stream --format {fmt}", shell=True,
                text=True, capture_output=True).stdout
            total = sum(
                to_bytes(line.split("\t")[1].split("/")[0])
                for line in out.splitlines()
                if line.startswith("llmdata-") and "\t" in line
            )
            self.rows.append((int(time.time()), total))
            self.peak = max(self.peak, total)
            self.halt.wait(2)


def run_dag(dag: str, conf: dict[str, Any] | None = None,
            wait: bool = True) -> str:
    flag = "" if wait else " --no-wait"
    out = sh(f"uv run --frozen python tools/airflow_run.py {dag}"
             f" --conf '{json.dumps(conf or {})}'{flag}")
    found = re.search(r"RUN_ID=(\S+)", out)
    return found.group(1) if found else ""


def sql(db: str, query: str) -> str:
    return sh(f'{PSQL} -d {db} -c "{query}"')


def index_hash() -> str:
    return sh("make -s index-hash")


def watermark() -> str:
    return sh("make -s watermark")


def compare() -> dict[str, Any]:
    out = sh("uv run --frozen python -m llmdata.freshness compare",
             check=False)
    try:
        return dict(json.loads(out.splitlines()[-1]))
    except (ValueError, IndexError):
        return {"match": False, "error": out[-300:]}


def disk_bytes() -> float:
    total = 0.0
    for image in ["llmdata-airflow:local", PG_IMAGE]:
        total += float(sh(f"docker image inspect -f '{{{{.Size}}}}'"
                          f" {image}"))
    for volume in ("llmdata_pgdata", "llmdata_models"):
        out = sh(f"docker run --rm --user 0 -v {volume}:/v:ro"
                 " --entrypoint du llmdata-airflow:local -sb /v")
        total += float(out.split()[0])
    return total


def facts() -> None:
    proc = Path("/proc/version")
    results["facts"].update({
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": sh("git rev-parse HEAD", check=False),
        "platform": platform.platform(),
        "cpus": os.cpu_count(),
        "wsl": proc.exists() and "microsoft" in proc.read_text().lower(),
        "ci": bool(os.environ.get("CI")),
        "docker": sh("docker version --format '{{.Server.Version}}'",
                     check=False),
        "docker_cpus_and_memory": sh(
            "docker info --format '{{.NCPU}} {{.MemTotal}}'", check=False),
    })


def s1() -> None:
    sh("make clean-all", check=False)
    timings = {"make up (cold, with build)": timed("make up")}
    watch = MemWatch()
    watch.start()
    timings["make data"] = timed("make data DAY=0")
    timings["full run, local model"] = full = timed(
        "make run PIPELINE=documents EMBEDDER=local")
    sh("make data DAY=1")
    timings["incremental run, day 1"] = timed(
        "make run PIPELINE=documents EMBEDDER=local")
    verify = subprocess.run("LLMDATA_REQUIRE_DB=1 make verify",
                            shell=True, capture_output=True, text=True)
    LOG[0].write(verify.stdout + verify.stderr)
    watch.halt.set()
    watch.join()
    (OUT / "s1-memory.csv").write_text("".join(
        f"{t},{b:.0f}\n" for t, b in watch.rows))
    disk = disk_bytes()
    results["facts"]["s1_timings_s"] = timings
    record("S-1", "peak core memory <= 6 GiB", watch.peak <= 6 * GIB,
           f"{watch.peak / GIB:.2f} GiB")
    record("S-1", "full run <= 30 min on a 4-CPU runner",
           full <= 1800, f"{full}s on {os.cpu_count()} CPUs")
    record("S-1", "images and volumes <= 10 GB", disk <= 10e9,
           f"{disk / 1e9:.2f} GB")
    record("S-1", "make verify passes", verify.returncode == 0,
           verify.stdout.strip().splitlines()[-1:] or "no output")
    bench = sh(f"{AIRFLOW} /opt/venv/bin/python -m llmdata.embed bench",
               check=False)  # information for Chapter 9, not a check
    results["facts"]["embedding_bench"] = bench.splitlines()
    results["facts"]["pgvector"] = sql(
        "llmdata", "SELECT extversion FROM pg_extension"
        " WHERE extname = 'vector'")
    for name in ("fake", "local"):  # switch models and back again
        results["facts"][f"reembed_{name}_s"] = timed(
            f"{AIRFLOW} /opt/venv/bin/python -m llmdata.embed reembed {name}")


def s2() -> None:
    executor = sh(f"{AIRFLOW} airflow config get-value core executor")
    record("S-2", "LocalExecutor", executor == "LocalExecutor", executor)
    url = sh(f"{AIRFLOW} airflow config get-value database"
             " sql_alchemy_conn")
    record("S-2", "metadata in Postgres", url.startswith("postgresql"),
           url.split("@")[-1])
    errors = sh(f"{AIRFLOW} airflow dags list-import-errors", check=False)
    record("S-2", "DAGs parse without import errors",
           "No data found" in errors or errors in ("", "[]"),
           errors[-200:] or "none")
    run_id = run_dag("retry_demo")
    tries = sql("airflow", "SELECT max(try_number) FROM task_instance"
                f" WHERE dag_id = 'retry_demo' AND run_id = '{run_id}'")
    record("S-2", "forced failure retries and succeeds", tries == "2",
           f"attempts={tries}")
    before = int(sql("airflow", "SELECT count(*) FROM dag_run"))
    sh(f"{COMPOSE} restart airflow")
    sh("uv run --frozen python tools/airflow_wait.py")
    after = int(sql("airflow", "SELECT count(*) FROM dag_run"))
    run_dag("retry_demo")
    record("S-2", "run history survives a restart",
           after >= before > 0, f"{before} runs before, {after} after")


def s4() -> None:
    fake = sh("uv run --frozen python -m llmdata.embed.fake --hash")
    record("S-4", "fake vectors match the recorded hash",
           fake == RECORDED_SAMPLE_HASH, fake[:16])
    sh(f"{AIRFLOW} /opt/venv/bin/python -m llmdata.embed.local"
       " warm-cache")
    out = sh(
        f"docker run --rm --network none --user {os.getuid()}:0"
        " -e HF_HUB_OFFLINE=1 -e PYTHONPATH=/opt/llmdata/src"
        " -e LLMDATA_MODEL_DIR=/opt/llmdata/models"
        " -v llmdata_models:/opt/llmdata/models"
        ' -v "$PWD/src:/opt/llmdata/src:ro"'
        " --entrypoint /opt/venv/bin/python llmdata-airflow:local"
        " -m llmdata.embed.local check", check=False)
    record("S-4", "local model loads from cache with no network",
           "dims=[384]" in out and "offline=True" in out, out[-100:])
    names = [line.split("=", 1)[0] for line in
             sh(f"{AIRFLOW} sh -c 'env | cut -d= -f1'",
                check=False).splitlines()]
    keys = [n for n in names
            if re.search(r"OPENAI|ANTHROPIC|API_KEY|HF_TOKEN", n)]
    record("S-4", "no API key in the stack", not keys,
           ", ".join(keys) or "none")


def s5() -> None:
    sh("make reset")
    run_dag("documents")
    first = index_hash()
    record("S-5", "day-0 index matches the source",
           bool(compare().get("match")), compare())
    sh("make data DAY=1")
    run_dag("documents")
    report = compare()
    record("S-5", "index matches the source after one run",
           bool(report.get("match")), report)
    sh("make data DAY=2")
    hash_before, mark_before = index_hash(), watermark()
    run_id = run_dag("documents", {"pause_at": "90-commit",
                                   "pause_s": 120}, wait=False)
    marker = Path("data") / f".pause-{run_id}"
    deadline = time.monotonic() + 1200
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(2)
    time.sleep(3)
    sh(f"{AIRFLOW} pkill -9 -f 'llmdata.pipeline stage documents"
       " 90-commit'", check=False)
    time.sleep(3)
    unchanged = (index_hash() == hash_before
                 and watermark() == mark_before)
    record("S-5", "killed run leaves index and watermark unchanged",
           marker.exists() and unchanged,
           f"paused={marker.exists()} unchanged={unchanged}")
    marker.unlink(missing_ok=True)
    resumed = subprocess.run(
        "uv run --frozen python tools/airflow_run.py documents"
        f" --attach {run_id}", shell=True).returncode == 0
    report = compare()
    record("S-5", "retry resumes and the index matches the source",
           resumed and bool(report.get("match")), report)
    hashes = []
    for _ in range(2):
        sh("make reset")
        run_dag("documents")
        hashes.append(index_hash())
    record("S-5", "two identical runs give the same index hash",
           hashes[0] == hashes[1] == first,
           " / ".join(h[:12] for h in [*hashes, first]))



CHUNK = Path("pipelines/documents/40-chunk.toml")
SCORES = "make -s scores"


def chunk_size(size: int) -> None:
    CHUNK.write_text(re.sub(r"params\.size = \d+",
                            f"params.size = {size}", CHUNK.read_text()))


def last_score() -> list[str]:
    return sh(SCORES).splitlines()[-1].split()


def s6() -> None:
    """One evaluation set version across chunk sizes and models."""
    found = results["facts"].setdefault("evaluation", {})
    try:
        for embedder in ("fake", "local"):
            for size in (900, 500, 1400):  # v1 is built at 900
                chunk_size(size)
                sh("make reset")
                run_dag("documents", {"embedder": embedder})
                run_dag("eval_sets", {"embedder": embedder})
                found[f"{embedder} {size}"] = " ".join(last_score())
    finally:
        chunk_size(900)
    versions = {row.split()[0] for row in found.values()}
    record("S-6", "one set version scored in all six cases",
           len(found) == 6 and versions == {"1"}, sorted(versions))
    sh("make reset")
    run_dag("documents", {"embedder": "local"})
    pages: dict[Path, str] = {}
    for row in sql("llmdata", "SELECT region, question || ' ' ||"
                   " evidence FROM evals.items").splitlines():
        region, pair = row.split("|", 1)
        page = Path(f"data/landing/guidelines/{region}/FAQ.html")
        pages[page] = pages.get(page, "<h1>Questions</h1>") + (
            f"<p>{pair}</p>")
    for page, html in pages.items():  # one FAQ page per region
        page.write_text(html)
    run_dag("documents", {"embedder": "local"})
    sh(f"{AIRFLOW} env LLMDATA_CONF='{{\"embedder\": \"local\"}}'"
       " /opt/venv/bin/python -m llmdata.pipeline stage eval_sets"
       " 30-score --run-id leak")  # the score without the check
    found["local 900 leaked"] = " ".join(last_score())
    refused = subprocess.run(
        "uv run --frozen python tools/airflow_run.py eval_sets"
        """ --conf '{"embedder": "local"}'""", shell=True,
        capture_output=True, text=True).returncode != 0
    record("S-6", "the check refuses a set found in the index",
           refused, found["local 900 leaked"])
    for page in pages:
        page.unlink()


def main() -> int:
    OUT.mkdir(exist_ok=True)
    LOG.append((OUT / "spike.log").open("w"))
    facts()
    for name, step in (("S-1", s1), ("S-2", s2), ("S-4", s4),
                       ("S-5", s5), ("S-6", s6)):
        try:
            step()
        except Exception as exc:  # recorded, then the next spike runs
            record(name, "completed without error", False,
                   str(exc)[-400:])
    results["facts"]["image_digests"] = {
        image: next((line.split()[-1] for line in sh(
            f"docker buildx imagetools inspect {image}", check=False
        ).splitlines() if line.startswith("Digest:")), "unknown")
        for image in IMAGES
    }
    (OUT / "summary.json").write_text(json.dumps(results, indent=1))
    rows = ["| Spike | Check | Result | Detail |", "|---|---|---|---|"]
    rows += [f"| {c['spike']} | {c['check']} | "
             f"{'PASS' if c['pass'] else 'FAIL'} | {c['detail']} |"
             for c in results["checks"]]
    text = "\n".join(rows) + "\n\n```json\n" + json.dumps(
        results["facts"], indent=1) + "\n```\n"
    (OUT / "summary.md").write_text(text)
    print(text)
    failed = [c for c in results["checks"] if not c["pass"]]
    return 1 if failed else 0  # a failed check fails the job


if __name__ == "__main__":
    raise SystemExit(main())
