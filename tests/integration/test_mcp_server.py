"""The triage tools over MCP: contracts out, errors explained."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from llmdata.config import Settings
from llmdata.db import connect

pytest.importorskip("mcp")  # the agents extra; CI runs it in a step


def tools(call: str = "", args: dict[str, Any] | None = None) -> Any:
    from mcp import Client

    from llmdata.agents.server import server

    async def go() -> Any:
        async with Client(server) as client:
            if call:
                return await client.call_tool(call, args or {})
            return await client.list_tools()

    return asyncio.run(go())


@pytest.mark.chapter(18)
def test_tools_publish_their_contracts(synced: Settings) -> None:
    found = {t.name: t for t in tools().tools}
    assert set(found) == {"claim_status", "search_documents"}
    schema = found["claim_status"].output_schema or {}
    assert {"status", "is_open", "as_of"} <= set(schema["properties"])


@pytest.mark.chapter(18)
def test_answers_carry_their_age_and_refusals_say_why(
    synced: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLMDATA_AGENT_REGION", "north")
    ok = tools("claim_status", {"claim_id": "CLM-00004"})
    assert not ok.is_error and ok.structured_content["as_of"]
    hits = tools("search_documents", {"query": "escape of water"})
    assert not hits.is_error and hits.structured_content["result"]
    south = tools("claim_status", {"claim_id": "CLM-00001"})
    assert south.is_error and "no claim" in south.content[0].text
    with connect(synced.dsn) as conn:
        conn.execute(
            "UPDATE agent.claim_facts"
            " SET read_at = read_at - interval '1 hour'"
        )
    old = tools("claim_status", {"claim_id": "CLM-00004"})
    assert old.is_error and "the limit is" in old.content[0].text
