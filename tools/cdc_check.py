"""The cdc profile end to end on a CI runner. Results go to cdc/."""

from __future__ import annotations

import ast
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "tools")
from spike import run_spike as base  # noqa: E402

OUT = Path("cdc")
COMPOSE = base.COMPOSE + " -f deploy/compose/cdc.yml"
AIRFLOW = f"{COMPOSE} exec -T airflow /opt/venv/bin/python"
TOPIC = "source.public.claims"
IMAGES = [
    "apache/kafka:4.3.1",
    "quay.io/debezium/connect:3.7.0.Final",
]
PROBE = """
import json
from confluent_kafka import Consumer, KafkaError, TopicPartition
c = Consumer({"bootstrap.servers": "kafka:9092", "group.id": "probe",
              "enable.partition.eof": True})
c.assign([TopicPartition("source.public.claims", 0, 0)])
ops, lags, END, first = {}, [], KafkaError._PARTITION_EOF, None
while True:
    m = c.poll(15)
    eof = m and m.error() and m.error().code() == END
    if m is None or eof:
        break
    if m.value() is None:
        ops["tombstone"] = ops.get("tombstone", 0) + 1
        continue
    e = json.loads(m.value())
    ops[e["op"]] = ops.get(e["op"], 0) + 1
    if e["op"] == "d":
        first = first or e["before"]
    if e["op"] != "r":
        lags.append(e["ts_ms"] - e["source"]["ts_ms"])
lags.sort()
print(json.dumps({"ops": ops, "delete_before": first, "capture_ms": {
    "median": lags[len(lags) // 2] if lags else None,
    "max": lags[-1] if lags else None, "events": len(lags)}}))
"""


def end_offset() -> int:
    out = base.sh(
        f"{COMPOSE} exec -T kafka /opt/kafka/bin/kafka-get-offsets.sh"
        f" --bootstrap-server kafka:9092 --topic {TOPIC}",
        check=False,
    )
    return sum(
        int(line.rsplit(":", 1)[1])
        for line in out.splitlines()
        if line.startswith(TOPIC)
    )


def settle(at_least: int, limit: float = 300) -> int:
    """Wait until the topic holds enough events and stops growing."""
    deadline, last = time.monotonic() + limit, -1
    while time.monotonic() < deadline:
        now = end_offset()
        if now >= at_least and now == last:
            return now
        last = now
        time.sleep(5)
    raise TimeoutError(f"topic stopped at {last}, wanted {at_least}")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    base.LOG.append((OUT / "cdc.log").open("w"))
    facts, record = base.results["facts"], base.record
    watch = base.MemWatch()
    try:
        base.sh("make clean-all PROFILE=cdc", check=False)
        watch.start()
        facts["make up PROFILE=cdc (s)"] = base.timed(
            "make up PROFILE=cdc"
        )
        base.sh("make data DAY=0")
        claims = int(
            base.sql("source", "SELECT count(*) FROM claims")
        )
        start = settle(claims)
        base.run_dag("documents")
        report = base.compare()
        record(
            "CDC",
            "day-0 index matches the source through Kafka",
            bool(report.get("match")),
            f"{start} events; {report}",
        )
        out = base.sh("make data DAY=1")
        done = ast.literal_eval(
            out.split("day 1: ")[1].splitlines()[0]
        )
        changes = done["claims_updated"] + done["claims_soft"]
        settle(start + changes + 2 * done["claims_hard"])
        base.run_dag("documents")
        report = base.compare()
        record(
            "CDC",
            "day-1 changes and deletions reach the index",
            bool(report.get("match")),
            f"{done}; {report}",
        )
        probe = json.loads(
            base.sh(f"{AIRFLOW} - <<'EOF'\n{PROBE}\nEOF")
        )
        facts["events"] = probe
        record(
            "CDC",
            "hard deletes arrive as delete events",
            probe["ops"].get("d") == done["claims_hard"],
            probe["ops"],
        )
        cid = base.sql(
            "source",
            "SELECT min(claim_id) FROM claims"
            " WHERE deleted_at IS NULL",
        )
        base.sql(
            "source", f"DELETE FROM claims WHERE claim_id = '{cid}'"
        )
        erased = base.sh(
            f"make -s erase KEY=claim:{cid} REQUEST=ER-0001"
        )
        base.run_dag("documents")
        found = base.sql(
            "llmdata",
            "SELECT count(*) FROM search_chunks"
            f" WHERE doc_key = 'claim:{cid}'",
        )
        report = base.compare()
        record(
            "CDC",
            "an erased claim is gone and stays gone",
            found == "0" and bool(report.get("match")),
            f"{erased}; {report}",
        )
        facts["lag"] = base.sh("make -s lag", check=False)
    except Exception as exc:  # recorded; the summary is still written
        record(
            "CDC", "completed without error", False, str(exc)[-600:]
        )
    watch.halt.set()
    if watch.is_alive():
        watch.join()
    record(
        "CDC",
        "peak memory with Kafka and Debezium <= 8 GiB",
        watch.peak <= 8 * base.GIB,
        f"{watch.peak / base.GIB:.2f} GiB",
    )
    facts["image_digests"] = {
        image: next(
            (
                line.split()[-1]
                for line in base.sh(
                    f"docker buildx imagetools inspect {image}",
                    check=False,
                ).splitlines()
                if line.startswith("Digest:")
            ),
            "unknown",
        )
        for image in IMAGES
    }
    rows = ["| Check | Result | Detail |", "|---|---|---|"]
    rows += [
        f"| {c['check']} | {'PASS' if c['pass'] else 'FAIL'} |"
        f" {c['detail']} |"
        for c in base.results["checks"]
    ]
    text = (
        "\n".join(rows)
        + "\n\n```json\n"
        + json.dumps(facts, indent=1)
        + "\n```\n"
    )
    (OUT / "summary.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
