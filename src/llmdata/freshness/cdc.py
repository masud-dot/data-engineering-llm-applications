"""CdcSource: claim changes read from Debezium's change topic."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from collections.abc import Iterator
from typing import Any

from llmdata.contracts import ClaimRecord, SourceItem, require
from llmdata.freshness.sources import Marks, WatermarkSource
from llmdata.ingest.sources import claim_item
from llmdata.pipeline.context import Context

TOPIC = "source.public.claims"
CONNECT = "http://connect:8083/connectors/claims"
DAY_MS = str(24 * 3600 * 1000)
PG = "io.debezium.connector.postgresql"

# region: connector
CONNECTOR = {
    "connector.class": f"{PG}.PostgresConnector",
    "plugin.name": "pgoutput",
    "database.hostname": "postgres",
    "database.user": "llmdata",
    "database.password": "${env:PGPASSWORD}",
    "database.dbname": "source",
    "table.include.list": "public.claims",
    "topic.prefix": "source",
    "slot.name": "llmdata_claims",
    "publication.autocreate.mode": "all_tables",
    "tombstones.on.delete": "true",
    "topic.creation.default.partitions": "1",
    "topic.creation.default.replication.factor": "1",
    "topic.creation.default.cleanup.policy": "compact",
    "topic.creation.default.segment.ms": DAY_MS,
    "topic.creation.default.max.compaction.lag.ms": DAY_MS,
}
# endregion


# region: change-event
def from_event(value: bytes | None) -> SourceItem | None:
    """One Debezium change event as a change to stage."""
    if value is None:
        return None  # Kafka's own tombstone, kept for compaction
    event = json.loads(value)
    if event["op"] == "d":
        return SourceItem(
            doc_key=f"claim:{event['before']['claim_id']}",
            op="delete",
            origin="claims",
            kind="record",
        )
    [record] = require(ClaimRecord, [event["after"]], "claim_id")
    return claim_item(record)


# endregion


def read(
    servers: str, start: dict[str, str]
) -> tuple[list[bytes | None], dict[str, str]]:
    """Every event after the stored offsets, and the new offsets."""
    from confluent_kafka import (
        OFFSET_BEGINNING,
        Consumer,
        KafkaError,
        TopicPartition,
    )

    consumer = Consumer(
        {
            "bootstrap.servers": servers,
            "group.id": "llmdata",
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            "enable.partition.eof": True,
        }
    )
    try:
        topic = consumer.list_topics(TOPIC, timeout=30).topics[TOPIC]
        if topic.error:
            raise RuntimeError(f"{TOPIC}: {topic.error}")
        ends = {
            p: consumer.get_watermark_offsets(
                TopicPartition(TOPIC, p), timeout=30
            )[1]
            for p in topic.partitions
        }
        first = {
            p: int(start.get(str(p), OFFSET_BEGINNING)) for p in ends
        }
        consumer.assign(
            [TopicPartition(TOPIC, p, o) for p, o in first.items()]
        )
        todo = {p for p, end in ends.items() if first[p] < end}
        values: list[bytes | None] = []
        while todo:
            msg = consumer.poll(30)
            if msg is None:
                raise TimeoutError(f"{TOPIC}: no events for 30 s")
            part, error = msg.partition(), msg.error()
            if error and error.code() == KafkaError._PARTITION_EOF:
                todo.discard(part)  # compaction may leave gaps
                continue
            if error:
                raise RuntimeError(str(error))
            if msg.offset() < ends[part]:
                values.append(msg.value())
            if msg.offset() + 1 >= ends[part]:
                todo.discard(part)
    finally:
        consumer.close()
    return values, {str(p): str(end) for p, end in ends.items()}


class CdcSource(WatermarkSource):
    """Files as before; claims from the change topic."""

    def claims(
        self, ctx: Context, marks: Marks, known: dict[str, str]
    ) -> Iterator[SourceItem]:
        start = marks.get("claims", (None, {}))[1]
        servers = str(ctx.params.get("kafka", "kafka:9092"))
        values, ends = read(servers, start)
        latest: dict[str, SourceItem] = {}
        for value in values:  # the last change to a claim wins
            item = from_event(value)
            if item:
                latest[item.doc_key] = item
        for key, item in sorted(latest.items()):
            if item.op == "delete":
                if key in known:
                    yield item
            elif known.get(key) != item.content_hash[:16]:
                yield item
        self._pending["claims"] = (None, ends)


def register(url: str = CONNECT, wait: float = 300) -> str:
    """Create or update the connector; wait until it runs."""
    body = json.dumps(CONNECTOR).encode()
    put = urllib.request.Request(
        f"{url}/config",
        data=body,
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    deadline = time.monotonic() + wait
    state: Any = "not reached"
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(put, timeout=10).close()
            with urllib.request.urlopen(
                f"{url}/status", timeout=10
            ) as resp:
                status = json.load(resp)
            tasks = [t["state"] for t in status["tasks"]]
            state = [status["connector"]["state"], *tasks]
            if tasks and set(state) == {"RUNNING"}:
                return "RUNNING"
        except OSError as exc:  # not up yet, or rebalancing
            state = str(exc)
        time.sleep(3)
    raise RuntimeError(f"connector not running: {state}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.freshness.cdc")
    parser.add_argument("command", choices=["register"])
    parser.add_argument("--url", default=CONNECT)
    args = parser.parse_args(argv)
    print(register(args.url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
