"""Find personal data in text, replace it, record what was found."""

from __future__ import annotations

import email
import re
from collections import Counter
from email.policy import default
from email.utils import parseaddr
from pathlib import Path

from psycopg.types.json import Jsonb

from llmdata.db import connect
from llmdata.pipeline.context import Context

# region: detectors
PATTERNS = {  # identifiers with a fixed shape
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "phone": re.compile(r"(?:\+44\s?|\b0)7\d{3}\s?\d{3}\s?\d{3}\b"),
}
CALLER = re.compile(
    r"\bCaller ([A-Z][\w'-]+(?: [A-Z][\w'-]+){1,2}) \("
)


def known_names(kind: str, path: Path | None, text: str) -> set[str]:
    """Names the source states: the caller, the sender."""
    names = set(CALLER.findall(text))
    if kind == "eml" and path is not None:
        msg = email.message_from_bytes(
            path.read_bytes(), policy=default
        )
        names.add(parseaddr(str(msg["From"] or ""))[0])
    return {n for n in names if n}


def redact(text: str, names: set[str]) -> tuple[str, Counter[str]]:
    """Replace each item with its kind; count what was replaced."""
    found: Counter[str] = Counter()
    for kind, pattern in PATTERNS.items():
        text, n = pattern.subn(f"[{kind.upper()}]", text)
        found[kind] += n
    for name in sorted(names, key=len, reverse=True):
        text, n = re.subn(rf"\b{re.escape(name)}\b", "[NAME]", text)
        found["name"] += n
    return text, +found


# endregion


class PrivacyError(RuntimeError):
    """Personal data was still found after redaction."""


# region: redact-stage
def run(ctx: Context) -> None:
    landing, totals = (
        ctx.settings.data_dir / "landing",
        Counter[str](),
    )
    with connect(ctx.settings.dsn) as conn:
        rows = conn.execute(
            "SELECT doc_key, kind, ref, cleaned, meta FROM staged"
            " WHERE run_id = %s AND op = 'upsert' ORDER BY doc_key",
            (ctx.run_id,),
        ).fetchall()
        for key, kind, ref, text, meta in rows:
            path = landing / ref if ref else None
            names = known_names(kind, path, text)
            clean, found = redact(text, names)
            left, _ = redact(clean, names)
            if left != clean:
                raise PrivacyError(f"{key}: personal data left")
            if found or "pii" not in meta:  # a rerun keeps counts
                meta = meta | {"pii": dict(found)}
            conn.execute(
                "UPDATE staged SET cleaned = %s, meta = %s"
                " WHERE run_id = %s AND doc_key = %s",
                (clean, Jsonb(meta), ctx.run_id, key),
            )
            totals += found
    print(f"redacted {dict(totals)} in {len(rows)} documents")


# endregion
