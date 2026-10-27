"""Clean stage: normalise text, drop boilerplate, mark copies."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

import py3langid
from psycopg.types.json import Jsonb

from llmdata.clean.dedup import Doc, duplicates, signature
from llmdata.db import Conn, connect
from llmdata.pipeline.context import Context

DERIVED = ("language", "edition", "minhash", "duplicate_of")


# region: cleaners
def clean_line(line: str) -> str:
    """Drop invisible characters, normalise, tidy the spaces."""
    kept = "".join(
        c  # categories C*: control, format, private, unassigned
        for c in line.replace("\t", " ")
        if unicodedata.category(c)[0] != "C"
    )
    return " ".join(unicodedata.normalize("NFKC", kept).split())


def clean_text(text: str, boilerplate: list[str]) -> str:
    rules = [re.compile(p, re.IGNORECASE) for p in boilerplate]
    out: list[str] = []
    for line in map(clean_line, text.splitlines()):
        if any(rule.match(line) for rule in rules):
            continue
        if line or (out and out[-1]):  # at most one blank line
            out.append(line)
    return "\n".join(out).strip()


def language(text: str) -> str:
    """ISO 639-1 code of the most likely language."""
    return str(py3langid.classify(text[:2000])[0])


# endregion


def scope(origin: str, meta: dict[str, Any]) -> str:
    """Copies are looked for only among documents that share this."""
    roles = ",".join(sorted(meta["roles"]))
    edition = meta.get("edition", "")
    return f"{origin}|{meta['region']}|{roles}|{edition}"


def indexed(
    conn: Conn, origins: list[str], skip: set[str]
) -> list[Doc]:
    """Signatures of published documents that are not copies."""
    rows = conn.execute(
        "SELECT doc_key, version, origin, meta FROM documents"
        " WHERE origin = ANY(%s) AND meta ? 'minhash'"
        " AND NOT meta ? 'duplicate_of'",
        (origins,),
    )
    return [
        Doc(k, v, scope(o, m), m["minhash"])
        for k, v, o, m in rows
        if k not in skip
    ]


ROWS = (
    "SELECT doc_key, origin, content_hash, parsed, meta FROM staged"
    " WHERE run_id = %s AND op = 'upsert' ORDER BY doc_key"
)
SAVE = (
    "UPDATE staged SET cleaned = %s, meta = %s"
    " WHERE run_id = %s AND doc_key = %s"
)


# region: clean-stage
def run(ctx: Context) -> None:
    rules = [str(p) for p in ctx.params.get("boilerplate", [])]
    origins = [str(o) for o in ctx.params.get("dedupe", [])]
    threshold = float(ctx.params.get("threshold", 0.8))
    edition = re.compile(str(ctx.params.get("edition", "(?!)")))
    done: dict[str, tuple[str, dict[str, Any]]] = {}
    new: list[Doc] = []
    with connect(ctx.settings.dsn) as conn:
        for key, origin, digest, parsed, meta in conn.execute(
            ROWS, (ctx.run_id,)
        ):
            text = clean_text(parsed or "", rules)
            meta = {k: v for k, v in meta.items() if k not in DERIVED}
            meta["language"] = language(text)
            if found := edition.search(text):
                meta["edition"] = found.group(1)
            if origin in origins:
                sig = meta["minhash"] = signature(text)
                where = scope(origin, meta)
                new.append(Doc(key, digest[:16], where, sig))
            done[key] = (text, meta)
        known = indexed(conn, origins, set(done))
        twins = duplicates(new, known, threshold)
        for key, twin in twins.items():
            copied = {"doc_key": twin.key, "version": twin.version}
            done[key][1]["duplicate_of"] = copied
        for key, (text, meta) in done.items():
            conn.execute(SAVE, (text, Jsonb(meta), ctx.run_id, key))
    langs = Counter(meta["language"] for _, meta in done.values())
    print(f"cleaned {len(done)} documents; languages {dict(langs)}")
    print(f"near-duplicates marked: {len(twins)}")


# endregion
