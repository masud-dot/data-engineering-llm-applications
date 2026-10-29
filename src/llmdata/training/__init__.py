"""Fine-tuning datasets: claim-note summaries, checked and clean."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from typing import Any

from llmdata.config import settings
from llmdata.db import Conn, connect
from llmdata.index import index_hash
from llmdata.pipeline.context import Context
from llmdata.privacy import CALLER, PATTERNS
from llmdata.training.teacher import get

SYSTEM = "Summarise the claim note for a claims handler."
FUNCTION_WORDS = {"a", "also", "an", "and", "mentions", "of", "the"}


def latest(conn: Conn, name: str) -> int | None:
    row = conn.execute(
        "SELECT max(version) FROM training.sets WHERE name = %s",
        (name,),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


NOTES = (
    "SELECT d.doc_key, d.version,"
    " string_agg(c.text, ' ' ORDER BY c.ordinal)"
    " FROM documents d JOIN search_chunks c USING (doc_key)"
    " WHERE d.origin = 'claims' GROUP BY 1, 2 ORDER BY 1"
)
ADD_SET = (
    "INSERT INTO training.sets (name, version, built_from, teacher)"
    " VALUES (%s, %s, %s, %s)"
)
TO_TRAIN = (
    "INSERT INTO training.examples VALUES (%(n)s, %(v)s, %(id)s,"
    " %(split)s, %(prompt)s, %(completion)s, %(key)s, %(dv)s, NULL)"
)
TO_TEST = (  # test examples are evaluation data, kept in evals
    "INSERT INTO evals.examples VALUES (%(n)s, %(v)s, %(id)s,"
    " %(prompt)s, %(completion)s, %(key)s, %(dv)s, NULL)"
)


# region: split-and-label
def split_of(doc_key: str) -> str:
    """The claim decides the split, so its versions stay together."""
    number = int(hashlib.sha256(doc_key.encode()).hexdigest(), 16)
    return {0: "test", 1: "validation"}.get(number % 10, "train")


def build(ctx: Context) -> None:
    """A new version: published claim notes, split and labelled."""
    name = str(ctx.params["name"])
    teacher = get(ctx.params["teacher"])
    found: Counter[str] = Counter()
    with connect(ctx.settings.dsn) as conn:
        version = (latest(conn, name) or 0) + 1
        built = index_hash(conn)[0][:12]
        conn.execute(ADD_SET, (name, version, built, teacher.id))
        for key, doc_version, note in conn.execute(NOTES).fetchall():
            split = split_of(key)
            row = {"n": name, "v": version, "split": split}
            row |= {"key": key, "dv": doc_version, "prompt": note}
            row["id"] = hashlib.sha256(key.encode()).hexdigest()[:12]
            row["completion"] = teacher.summarise(note)
            table = TO_TEST if split == "test" else TO_TRAIN
            conn.execute(table, row)
            found[split] += 1
    print(f"{name} v{version}: {dict(sorted(found.items()))}")


# endregion


STORES = {
    "evals.examples": "reference",
    "training.examples": "completion",
}
MINE = " WHERE (name, version) = (%s, %s) ORDER BY 1"
REJECT = (
    "UPDATE {} SET rejected = %s"
    " WHERE (name, version, example_id) = (%s, %s, %s)"
)


# region: example-checks
def problem(prompt: str, completion: str) -> str | None:
    """Why an example must not be used, or None."""
    if not completion or len(completion) >= len(prompt):
        return "summary empty or not shorter than the note"
    if set(words(completion)) - set(words(prompt)) - FUNCTION_WORDS:
        return "summary says what the note does not"
    text = f"{prompt}\n{completion}"
    if CALLER.search(text) or any(
        p.search(text) for p in PATTERNS.values()
    ):
        return "personal data"
    return None


def check(ctx: Context) -> None:
    """Reject failing examples in both stores, and repeated notes."""
    name, seen = str(ctx.params["name"]), set()
    rejected: Counter[str] = Counter()
    with connect(ctx.settings.dsn) as conn:
        version = latest(conn, name)
        for table, column in STORES.items():  # test examples first
            sql = f"SELECT example_id, prompt, {column} FROM {table}"
            rows = conn.execute(sql + MINE, (name, version))
            for eid, prompt, completion in rows.fetchall():
                note = " ".join(words(prompt))
                why = problem(prompt, completion) or (
                    "duplicate note" if note in seen else None
                )
                seen.add(note)
                if why:
                    rejected[why] += 1
                    args = (why, name, version, eid)
                    conn.execute(REJECT.format(table), args)
    print(f"{name} v{version}: rejected {dict(rejected) or 'none'}")


# endregion


CANDIDATES = (
    "SELECT example_id, prompt || ' ' || completion"
    " FROM training.examples WHERE (name, version) = (%s, %s)"
    " AND rejected IS NULL"
)
DROP = (
    "UPDATE training.examples SET rejected = %s"
    " WHERE (name, version) = (%s, %s) AND example_id = ANY(%s)"
)
OVERLAP = "overlaps evaluation data"


# region: decontaminate
EVALUATION = (  # every evaluation text, from every set and version
    "SELECT prompt || ' ' || reference FROM evals.examples"
    " UNION ALL SELECT question || ' ' || evidence FROM evals.items"
)


def ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    w = words(text)
    return {tuple(w[i : i + n]) for i in range(len(w) - n + 1)}


def decontaminate(ctx: Context) -> None:
    """Drop examples sharing n words in a row with evaluation data."""
    name, n = str(ctx.params["name"]), int(ctx.params["n"])
    with connect(ctx.settings.dsn) as conn:
        version = latest(conn, name)
        held: set[tuple[str, ...]] = set()
        for (text,) in conn.execute(EVALUATION):
            held |= ngrams(text, n)
        rows = conn.execute(CANDIDATES, (name, version)).fetchall()
        hits = [eid for eid, text in rows if ngrams(text, n) & held]
        conn.execute(DROP, (OVERLAP, name, version, hits))
    print(f"{name} v{version}: {len(hits)} of {len(rows)} overlap")


# endregion


KEPT = (
    "SELECT prompt, completion, doc_key || '@' || doc_version"
    " FROM training.examples WHERE (name, version, split)"
    " = (%s, %s, %s) AND rejected IS NULL ORDER BY example_id"
)
REJECTED = (
    "SELECT rejected, count(*) FROM training.examples"
    " WHERE (name, version) = (%s, %s) AND rejected IS NOT NULL"
    " GROUP BY 1 ORDER BY 1"
)


def chat(prompt: str, completion: str) -> str:
    """One example in the chat format most fine-tuning tools read."""
    turns = [("system", SYSTEM), ("user", prompt)]
    turns.append(("assistant", completion))
    messages = [{"role": r, "content": c} for r, c in turns]
    return json.dumps({"messages": messages}) + "\n"


# region: publish
def publish(ctx: Context) -> None:
    """Write the files and their manifest once; never rewrite them."""
    name = str(ctx.params["name"])
    with connect(ctx.settings.dsn) as conn:
        version = latest(conn, name)
        out = ctx.settings.data_dir / f"datasets/{name}/v{version}"
        if out.exists():
            return
        tmp = out.with_name(f"{out.name}.tmp")
        tmp.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, Any] = {"name": name, "version": version}
        manifest |= {"files": {}, "documents": []}
        for split in ("train", "validation"):
            found = conn.execute(KEPT, (name, version, split))
            rows = found.fetchall()
            text = "".join(chat(p, c) for p, c, _ in rows)
            (tmp / f"{split}.jsonl").write_text(text)
            digest = hashlib.sha256(text.encode()).hexdigest()
            entry = {"examples": len(rows), "sha256": digest}
            manifest["files"][f"{split}.jsonl"] = entry
            manifest["documents"] += [doc for _, _, doc in rows]
        reasons = conn.execute(REJECTED, (name, version)).fetchall()
        manifest["rejected"] = dict(reasons)
        text = json.dumps(manifest, indent=1)
        (tmp / "manifest.json").write_text(text)
    os.replace(tmp, out)  # the version appears whole or not at all
    files = manifest["files"]
    done = [f"{e['examples']} in {f}" for f, e in files.items()]
    print(f"{name} v{version}: {', '.join(done)}")


# endregion


SHOW = (
    "SELECT s.version, s.teacher, s.built_from,"
    " count(*) FILTER (WHERE e.split = 'train'"
    " AND e.rejected IS NULL),"
    " count(*) FILTER (WHERE e.split = 'validation'"
    " AND e.rejected IS NULL),"
    " (SELECT count(*) FROM evals.examples x WHERE (x.name,"
    " x.version) = (s.name, s.version) AND x.rejected IS NULL),"
    " count(*) FILTER (WHERE e.rejected IS NOT NULL)"
    " FROM training.sets s LEFT JOIN training.examples e"
    " USING (name, version) WHERE s.name = %s"
    " GROUP BY s.name, s.version, s.teacher, s.built_from"
    " ORDER BY s.version"
)


def show(name: str) -> list[tuple[Any, ...]]:
    with connect(settings().dsn) as conn:
        return conn.execute(SHOW, (name,)).fetchall()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.training")
    parser.add_argument("command", choices=["show"])
    parser.add_argument("name", nargs="?", default="summaries")
    args = parser.parse_args(argv)
    for row in show(args.name):
        print("  ".join(str(v) for v in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
