"""The triage agent's tools over MCP. Needs the agents extra."""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from llmdata import agents
from llmdata.config import settings
from llmdata.db import connect
from llmdata.embed import get

# region: mcp-server
server = MCPServer(
    "quillmere-triage",
    instructions="Claims facts and documents for one region's"
    " triage. Every result says when it was true.",
)


def reader() -> tuple[str, str]:
    """Set by whoever deploys the agent, never by the model."""
    return os.environ.get("LLMDATA_AGENT_REGION", ""), "claims"


@server.tool()
def claim_status(claim_id: str) -> agents.ClaimStatus:
    """One claim's status and when it was true, within 15 minutes."""
    with connect(settings().dsn) as conn:
        agents.as_reader(conn, *reader())
        try:
            found = agents.claim_status(conn, claim_id)
        except agents.StaleData as exc:
            raise ToolError(f"{exc}; ask again later") from exc
    if found is None:
        raise ToolError(f"no claim {claim_id} for this agent")
    return found


@server.tool()
def search_documents(query: str, k: int = 5) -> list[agents.Passage]:
    """Redacted passages this agent may read, best match first."""
    embedder = get(os.environ.get("EMBEDDER", "fake"))
    with connect(settings().dsn) as conn:
        agents.as_reader(conn, *reader())
        try:
            return agents.search(conn, embedder, query, k)
        except agents.StaleData as exc:
            raise ToolError(str(exc)) from exc


# endregion

if __name__ == "__main__":
    server.run()
