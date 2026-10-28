"""Checks on a run's staged data: counts, a profile and drift."""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llmdata.db import Conn
from llmdata.parse import MIN_CHARS, PypdfParser


@dataclass(frozen=True)
class Result:
    name: str
    scope: str
    value: float
    bound: float | None
    passed: bool


# region: count-checks
COUNTS = {  # each counts problems in the run, and must find none
    "documents without chunks": (
        "SELECT count(*) FROM staged s WHERE s.run_id = %(r)s"
        " AND s.op = 'upsert' AND NOT EXISTS (SELECT 1"
        " FROM staged_chunks c WHERE c.run_id = s.run_id"
        " AND c.doc_key = s.doc_key)"
    ),
    "chunks without ids or vectors": (
        "SELECT count(*) FROM staged_chunks WHERE run_id = %(r)s"
        " AND (chunk_id IS NULL OR embedding IS NULL)"
    ),
    "oversized chunks": (
        "SELECT count(*) FROM staged_chunks WHERE run_id = %(r)s"
        " AND length(text) > %(max_chunk_chars)s"
    ),
    "vectors off unit length": (
        "SELECT count(*) FROM staged_chunks WHERE run_id = %(r)s"
        " AND abs(vector_norm(embedding) - 1) > 0.01"
    ),
    "vectors shared by different texts": (
        "SELECT count(*) FROM (SELECT embedding FROM staged_chunks"
        " WHERE run_id = %(r)s GROUP BY embedding"
        " HAVING count(DISTINCT text) > 1) AS shared"
    ),
    "documents that lost text": (
        "SELECT count(*) FROM (SELECT doc_key, sum(length(text)) n"
        " FROM staged_chunks WHERE run_id = %(r)s GROUP BY doc_key)"
        " s JOIN (SELECT doc_key, sum(length(text)) n FROM chunks"
        " GROUP BY doc_key) i USING (doc_key)"
        " WHERE s.n < i.n * (1 - %(max_shrink)s)"
    ),
}
# endregion
NEAR_EMPTY = (
    "SELECT count(*) FILTER (WHERE length(cleaned) < %(min_chars)s),"
    " count(*) FROM staged WHERE run_id = %(r)s AND op = 'upsert'"
)


def counts(
    conn: Conn, run_id: str, p: dict[str, Any]
) -> list[Result]:
    args = p | {"r": run_id}
    results = []
    for name, sql in COUNTS.items():
        row = conn.execute(sql, args).fetchone()
        found = int(row[0]) if row else 0
        results.append(Result(name, "", found, 0, found == 0))
    row = conn.execute(NEAR_EMPTY, args).fetchone()
    share = row[0] / row[1] if row and row[1] else 0.0
    bound = float(p["max_near_empty"])
    results.append(
        Result(
            "near-empty documents", "", share, bound, share <= bound
        )
    )
    return results


# region: run-profile
PROFILE = (
    "SELECT origin, count(*), percentile_cont(0.5) WITHIN GROUP"
    " (ORDER BY length(cleaned)) FROM staged WHERE run_id = %(r)s"
    " AND op = 'upsert' GROUP BY origin"
)
REGIONS = (
    "SELECT meta ->> 'region', count(*)::float / sum(count(*))"
    " OVER () FROM staged WHERE run_id = %(r)s AND op = 'upsert'"
    " AND origin = 'claims' GROUP BY 1"
)
PDFS = (
    "SELECT origin, ref FROM staged WHERE run_id = %(r)s"
    " AND op = 'upsert' AND kind = 'pdf'"
)


def profile(
    conn: Conn, run_id: str, landing: Path
) -> dict[tuple[str, str], float]:
    """This run's measures, by name and by origin or region."""
    found: dict[tuple[str, str], float] = {}
    for origin, docs, chars in conn.execute(PROFILE, {"r": run_id}):
        found[("documents", origin)] = docs
        found[("characters per document", origin)] = chars
    for region, share in conn.execute(REGIONS, {"r": run_id}):
        found[("share of claims", region)] = share
    pages: Counter[str] = Counter()
    scanned: Counter[str] = Counter()
    for origin, ref in conn.execute(PDFS, {"r": run_id}):
        texts = PypdfParser().pages(landing / ref)
        pages[origin] += len(texts)
        scanned[origin] += sum(
            len(t.strip()) < MIN_CHARS for t in texts
        )
    for origin, total in pages.items():
        found[("share of pages scanned", origin)] = (
            scanned[origin] / total
        )
    return found


# endregion


# region: drift
BASELINE = (
    "SELECT q.value FROM quality_results q"
    " JOIN ledger l ON l.run_id = q.run_id"
    " JOIN quality_results d ON d.run_id = q.run_id"
    " AND d.name = 'documents' AND d.scope = %(origin)s"
    " WHERE l.status = 'succeeded' AND q.name = %(name)s"
    " AND q.scope = %(scope)s AND d.value >= %(min_docs)s"
    " ORDER BY l.finished_at DESC LIMIT %(window)s"
)
RELATIVE = {"characters per document"}  # the rest compare shares


def drift(
    conn: Conn, now: dict[tuple[str, str], float], p: dict[str, Any]
) -> list[Result]:
    """Compare each measure with recent good runs of enough size."""
    results = []
    for (name, scope), value in sorted(now.items()):
        origin = "claims" if name == "share of claims" else scope
        if (
            name == "documents"
            or now["documents", origin] < p["min_docs"]
        ):
            continue  # too few documents to judge
        args = p | {"name": name, "scope": scope, "origin": origin}
        past = [float(v) for (v,) in conn.execute(BASELINE, args)]
        if not past:
            continue  # nothing to compare with yet
        base = statistics.median(past)
        change, bound = abs(value - base), p["max_share_change"]
        if name in RELATIVE:
            change, bound = change / (base or 1.0), p["max_change"]
        passed = change <= bound
        results.append(
            Result(f"{name} drift", scope, change, bound, passed)
        )
    return results


# endregion
