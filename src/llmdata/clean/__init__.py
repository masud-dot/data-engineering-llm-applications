"""Clean stage: normalise text and drop boilerplate lines."""

from __future__ import annotations

import re
import unicodedata

from llmdata.db import connect
from llmdata.pipeline.context import Context


def clean_text(text: str, boilerplate: list[str]) -> str:
    patterns = [re.compile(p, re.IGNORECASE) for p in boilerplate]
    out: list[str] = []
    for line in unicodedata.normalize("NFKC", text).splitlines():
        line = " ".join(line.split())
        if any(p.match(line) for p in patterns):
            continue
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def run(ctx: Context) -> None:
    rules = [str(p) for p in ctx.params.get("boilerplate", [])]
    with connect(ctx.settings.dsn) as conn:
        rows = conn.execute(
            "SELECT doc_key, parsed FROM staged WHERE run_id = %s"
            " AND op = 'upsert' AND cleaned IS NULL",
            (ctx.run_id,),
        ).fetchall()
        for key, parsed in rows:
            conn.execute(
                "UPDATE staged SET cleaned = %s"
                " WHERE run_id = %s AND doc_key = %s",
                (clean_text(parsed or "", rules), ctx.run_id, key),
            )
    print(f"cleaned {len(rows)} documents")
