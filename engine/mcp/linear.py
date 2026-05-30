"""Linear ticketing provider — wrapper around Linear MCP server."""

from __future__ import annotations

from .types import Ticket, TicketComment  # noqa: F401  (re-exported / type contract)


class LinearProvider:
    name = "linear"

    def __init__(self, config: dict):
        self.config = config
        self.workspace = config.get("workspace")
        self.default_project = config.get("default-project")
        self.mcp_tool_prefix = config.get("mcp-tool-prefix", "mcp__claude_ai_Linear")
        # TODO Phase 5: real connection via Linear MCP server.
        # Linear exposes GraphQL-backed tools (issue_get, issue_search,
        # comment_create). Credentials from $LINEAR_API_KEY env var.

    def fetch_ticket(self, ticket_id: str) -> Ticket:
        # TODO Phase 5: call MCP `linear_issue_get` with {id}.
        raise NotImplementedError(
            f"LinearProvider.fetch_ticket({ticket_id!r}) — Phase 5 (MCP wiring pending)"
        )

    def list_tickets(self, filters: dict) -> list[Ticket]:
        # TODO Phase 5: translate `filters` into Linear's filter DSL.
        raise NotImplementedError("LinearProvider.list_tickets — Phase 5 (MCP wiring pending)")

    def post_comment(self, ticket_id: str, body: str) -> None:
        # TODO Phase 5: call MCP `linear_comment_create`.
        raise NotImplementedError(
            f"LinearProvider.post_comment({ticket_id!r}) — Phase 5 (MCP wiring pending)"
        )
