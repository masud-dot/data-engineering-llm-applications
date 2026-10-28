"""No customer detail in the index; the database checks access."""

from __future__ import annotations

import re
from typing import Any

import psycopg
import pytest

from llmdata.config import Settings
from llmdata.db import Conn, connect
from llmdata.pipeline.__main__ import main as pipeline
from llmdata.synthetic import FIRST, LAST

PEOPLE = re.compile(
    rf"\b(?:{'|'.join(FIRST)}) (?:{'|'.join(LAST)})\b"
    r"|7700 ?900|@example\.com"
)


def query(dsn: str, sql: str, *args: Any) -> list[Any]:
    with connect(dsn) as conn:
        return [row[0] for row in conn.execute(sql, args)]


def as_reader(
    conn: Conn, region: str | None, role: str | None
) -> None:
    conn.execute("SET ROLE llmdata_reader")
    if region and role:
        conn.execute(
            "SELECT set_config('llmdata.region', %s, false),"
            " set_config('llmdata.role', %s, false)",
            (region, role),
        )


@pytest.fixture
def day0(
    landed: Settings, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    monkeypatch.setenv("LLMDATA_DATA_DIR", str(landed.data_dir))
    assert pipeline(["run", "documents", "--run-id", "r0"]) == 0
    return landed


# region: permission-tests
@pytest.mark.chapter(15)
def test_no_chunk_holds_a_customer_detail(day0: Settings) -> None:
    texts = query(day0.dsn, "SELECT text FROM chunks")
    assert texts and not [t for t in texts if PEOPLE.search(t)]


@pytest.mark.chapter(15)
def test_database_checks_access_on_every_chunk(
    day0: Settings,
) -> None:
    with connect(day0.dsn) as conn:
        [vector] = conn.execute(
            "SELECT embedding FROM chunks LIMIT 1"
        )
        as_reader(conn, None, None)
        assert conn.execute(
            "SELECT count(*) FROM chunks"
        ).fetchone() == (0,)
    with connect(day0.dsn) as conn:
        as_reader(conn, "north", "underwriter")
        seen = conn.execute(
            "SELECT region, roles FROM chunks"
        ).fetchall()
        assert seen and all(
            r == "north" and "underwriter" in roles
            for r, roles in seen
        )
        found = conn.execute(
            "SELECT count(*) FROM search(%s, 'south', 'claims', 5)",
            (vector[0],),
        ).fetchone()
        assert found == (0,)  # its arguments cannot widen access


# endregion


@pytest.mark.chapter(15)
def test_reader_search_is_recorded(day0: Settings) -> None:
    with connect(day0.dsn) as conn:
        [vector] = conn.execute(
            "SELECT embedding FROM chunks LIMIT 1"
        )
        as_reader(conn, None, None)
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("SELECT * FROM reader_search(%s)", vector)
    with connect(day0.dsn) as conn:
        as_reader(conn, "north", "claims")
        hits = conn.execute(
            "SELECT chunk_id FROM reader_search(%s, 3)", vector
        ).fetchall()
    assert query(day0.dsn, "SELECT chunk_ids FROM access_log") == [
        [h for (h,) in hits]
    ]
