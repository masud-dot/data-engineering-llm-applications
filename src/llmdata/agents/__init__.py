"""Data for the claims-triage agent: governed, fresh, permitted."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import ClassVar, Literal

from pydantic import BaseModel

from llmdata.contracts import Region
from llmdata.db import Conn, connect
from llmdata.embed import Embedder, model_id
from llmdata.pipeline.context import Context


class StaleData(RuntimeError):
    """The data is older than the tool may use."""


# region: claim-facts-sync
SOURCE = (
    "SELECT claim_id, policy_id, region, status, updated_at,"
    " transaction_timestamp() FROM claims WHERE deleted_at IS NULL"
)
COPY = "INSERT INTO agent.claim_facts VALUES (%s, %s, %s, %s, %s, %s)"


def sync(ctx: Context) -> None:
    """Replace the agent's copy of claim facts in one transaction."""
    with connect(ctx.settings.source_dsn, vectors=False) as source:
        rows = source.execute(SOURCE).fetchall()
    with connect(ctx.settings.dsn) as conn:
        conn.execute("DELETE FROM agent.claim_facts")
        with conn.cursor() as cur:
            cur.executemany(COPY, rows)
    print(f"claim facts: {len(rows)} claims copied")


# endregion


def fresh(age: timedelta, limit: timedelta, what: str) -> None:
    if age > limit:
        raise StaleData(f"{what} is {age} old; the limit is {limit}")


# region: claim-status-tool
class ClaimStatus(BaseModel):
    """What the triage agent may know of a claim, and when."""

    max_age: ClassVar[timedelta] = timedelta(minutes=15)
    claim_id: str
    policy_id: str
    region: Region
    status: Literal["open", "assessing", "settled", "closed"]
    is_open: bool
    changed_at: datetime
    as_of: datetime


def as_reader(conn: Conn, region: str, role: str) -> None:
    """Read as the agent; its deployment, not the model, says who."""
    conn.execute("SET ROLE llmdata_reader")
    conn.execute(
        "SELECT set_config('llmdata.region', %s, false),"
        " set_config('llmdata.role', %s, false)",
        (region, role),
    )


def claim_status(conn: Conn, claim_id: str) -> ClaimStatus | None:
    """None when the claim is unknown or not this reader's to see."""
    row = conn.execute(
        "SELECT claim_id, policy_id, region, status, is_open,"
        " changed_at, as_of, age FROM agent.claims"
        " WHERE claim_id = %s",
        (claim_id,),
    ).fetchone()
    if row is None:
        return None
    fresh(row[-1], ClaimStatus.max_age, f"claim {claim_id}")
    fields = zip(ClaimStatus.model_fields, row[:-1], strict=True)
    return ClaimStatus(**dict(fields))


# endregion


class Passage(BaseModel):
    """Redacted text this reader may see, and when it was read."""

    max_age: ClassVar[timedelta] = timedelta(hours=4)
    chunk_id: str
    doc_key: str
    text: str
    distance: float
    as_of: datetime


INDEX_AGE = "SELECT as_of, age FROM agent.index_freshness"
FOUND = (
    "SELECT chunk_id, doc_key, text, distance"
    " FROM reader_search(%s, %s)"
)


def search(
    conn: Conn, embedder: Embedder, query: str, k: int
) -> list[Passage]:
    """Chapter 15's audited search, refused when the index is old."""
    as_of, age = conn.execute(INDEX_AGE).fetchone() or (None, None)
    if as_of is None:
        raise StaleData("the index has never been published")
    fresh(age, Passage.max_age, "the index")
    made = conn.execute("SELECT DISTINCT embedding_model FROM chunks")
    if {m for (m,) in made} != {model_id(embedder)}:
        raise RuntimeError("the index was embedded by another model")
    vector = embedder.embed([query])[0]
    rows = conn.execute(FOUND, (vector, k)).fetchall()
    return [
        Passage(
            chunk_id=c, doc_key=d, text=t, distance=x, as_of=as_of
        )
        for c, d, t, x in rows
    ]
