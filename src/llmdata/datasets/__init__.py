"""Evaluation sets: build a version, check it, score the index."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from typing import Any

from llmdata.config import settings
from llmdata.db import Conn, connect
from llmdata.embed import choose, get, model_id
from llmdata.index import index_hash
from llmdata.pipeline.context import Context

ROW = re.compile(
    r"^\| (?P<cover>[^|]+?) \| (?P<limit>GBP \d+) \|"
    r" (?P<excess>GBP \d+) \| (?P<exclusion>[^|]+?) \|$",
    re.M,
)
QUESTION = (
    "What excess applies to {cover} cover with a {limit} limit?"
)


class LeakError(RuntimeError):
    """Evaluation questions were found in the index they test."""


class StaleError(RuntimeError):
    """Too many items label document versions no longer published."""


def current(conn: Conn, name: str) -> int | None:
    row = conn.execute(
        "SELECT max(version) FROM evals.sets WHERE name = %s", (name,)
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


# region: candidates
SOURCE = (
    "SELECT d.doc_key, d.version, c.region, c.text"
    " FROM search_chunks c JOIN documents d USING (doc_key)"
    " WHERE d.origin = 'wordings' AND c.section = '1. Cover'"
    " ORDER BY c.chunk_id"
)


def candidates(conn: Conn) -> list[dict[str, str]]:
    """One question per schedule row of each published wording."""
    found = []
    for key, version, region, text in conn.execute(SOURCE):
        for row in ROW.finditer(text):
            found.append(
                {
                    "question": QUESTION.format(**row.groupdict()),
                    "region": region,
                    "role": "underwriter",
                    "evidence": row.group(0),
                    "doc_key": key,
                    "doc_version": version,
                }
            )
    return found


# endregion


# region: build-set
ADD_SET = (
    "INSERT INTO evals.sets (name, version, digest, items,"
    " built_from) VALUES (%s, %s, %s, %s, %s)"
)
ADD_ITEM = (
    "INSERT INTO evals.items VALUES (%(n)s, %(v)s, %(id)s,"
    " %(question)s, %(region)s, %(role)s, %(evidence)s,"
    " %(doc_key)s, %(doc_version)s)"
)


def digest(data: object) -> str:
    text = json.dumps(data, sort_keys=True).encode()
    return hashlib.sha256(text).hexdigest()


def build(ctx: Context) -> None:
    """Create version 1, or a new version when asked to rebuild."""
    name = str(ctx.params["name"])
    with connect(ctx.settings.dsn) as conn:
        latest = current(conn, name)
        if latest and not ctx.conf.get("rebuild"):
            print(f"{name} v{latest} kept; rebuild to replace it")
            return
        pool = candidates(conn)
        rng = random.Random(int(ctx.params["seed"]))
        size = min(int(ctx.params["size"]), len(pool))
        items = sorted(rng.sample(pool, size), key=digest)
        version, built = (latest or 0) + 1, index_hash(conn)[0][:12]
        conn.execute(
            ADD_SET, (name, version, digest(items)[:16], size, built)
        )
        for item in items:
            ids = {"n": name, "v": version, "id": digest(item)[:12]}
            conn.execute(ADD_ITEM, item | ids)
    print(
        f"{name} v{version}: {size} items from {len(pool)} candidates"
    )


# endregion


# region: check-set
STALE = (
    "SELECT count(*) FILTER (WHERE NOT EXISTS (SELECT 1"
    " FROM documents d WHERE (d.doc_key, d.version)"
    " = (i.doc_key, i.doc_version))), count(*) FROM evals.items i"
    " WHERE (i.name, i.version) = (%(n)s, %(v)s)"
)
LEAKED = (
    "SELECT count(*) FROM evals.items i"
    " WHERE (i.name, i.version) = (%(n)s, %(v)s) AND EXISTS ("
    " SELECT 1 FROM search_chunks c"
    " WHERE strpos(lower(c.text), lower(i.question)) > 0)"
)


def check(ctx: Context) -> None:
    """Refuse a set found in the index, or one too stale to score."""
    name = str(ctx.params["name"])
    bound = float(ctx.conf.get("max_stale", ctx.params["max_stale"]))
    with connect(ctx.settings.dsn) as conn:
        args = {"n": name, "v": current(conn, name)}
        [(leaked,)] = conn.execute(LEAKED, args).fetchall()
        [(stale, size)] = conn.execute(STALE, args).fetchall()
    if leaked:
        raise LeakError(f"{leaked} questions of {name} are indexed")
    if stale > bound * size:
        raise StaleError(f"{stale} of {size} items stale; rebuild")
    print(f"{name} v{args['v']}: no leaks; {stale} of {size} stale")


# endregion


# region: rank-item
HITS = (
    "SELECT c.text FROM hybrid_search(%s, %s, %s, %s, %s) h"
    " JOIN search_chunks c USING (chunk_id)"
    " ORDER BY h.score DESC, chunk_id"
)


def rank(
    conn: Conn, vector: Any, item: tuple[Any, ...], k: int
) -> int:
    """Position of the first result that holds the evidence, or 0."""
    _, question, region, role, evidence = item
    rows = conn.execute(HITS, (question, vector, region, role, k))
    found = [
        n for n, (text,) in enumerate(rows, 1) if evidence in text
    ]
    return found[0] if found else 0


# endregion


LIVE = (
    "SELECT item_id, question, region, role, evidence"
    " FROM evals.items i WHERE (name, version) = (%s, %s)"
    " AND EXISTS (SELECT 1 FROM documents d"
    " WHERE (d.doc_key, d.version) = (i.doc_key, i.doc_version))"
    " ORDER BY item_id"
)
MODELS = "SELECT DISTINCT embedding_model FROM chunks"
SAVE = (
    "INSERT INTO evals.scores SELECT name, version, now(),"
    " %(built)s, %(model)s, %(k)s, %(done)s, items - %(done)s,"
    " %(recall)s, %(mrr)s, %(misses)s FROM evals.sets"
    " WHERE (name, version) = (%(name)s, %(v)s)"
)


# region: score-set
def score(ctx: Context) -> None:
    """Recall at k and mean reciprocal rank over live items."""
    name, k = str(ctx.params["name"]), int(ctx.params["k"])
    embedder = get(choose(ctx))
    model = model_id(embedder)
    with connect(ctx.settings.dsn) as conn:
        made = {str(m) for (m,) in conn.execute(MODELS)}
        if made != {model}:
            raise RuntimeError(
                f"index vectors are {made}, not {model}"
            )
        version = current(conn, name)
        items = conn.execute(LIVE, (name, version)).fetchall()
        vectors = embedder.embed([item[1] for item in items])
        ranks = [
            rank(conn, v, i, k)
            for v, i in zip(vectors, items, strict=True)
        ]
        n = len(ranks) or 1
        r: dict[str, Any] = {"name": name, "v": version, "k": k}
        r["done"], r["model"] = len(ranks), model
        r["recall"] = sum(x > 0 for x in ranks) / n
        r["mrr"] = sum(1 / x for x in ranks if x) / n
        r["misses"] = [
            i[0] for i, x in zip(items, ranks, strict=True) if not x
        ]
        r["built"] = index_hash(conn)[0][:12]
        conn.execute(SAVE, r)
    print(
        f"{name} v{version}: recall@{k} {r['recall']:.2f},"
        f" MRR {r['mrr']:.2f} over {n} items"
    )


# endregion


def scores(name: str) -> list[tuple[Any, ...]]:
    with connect(settings().dsn) as conn:
        return conn.execute(
            "SELECT version, model, index_hash, scored, stale,"
            " round(recall::numeric, 2), round(mrr::numeric, 2),"
            " cardinality(misses)"
            " FROM evals.scores WHERE name = %s ORDER BY scored_at",
            (name,),
        ).fetchall()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.datasets")
    parser.add_argument("command", choices=["scores"])
    parser.add_argument("name", nargs="?", default="schedules")
    args = parser.parse_args(argv)
    for row in scores(args.name):
        print("  ".join(str(v) for v in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
