"""Jira ticketing provider — wrapper around Atlassian MCP server."""

from __future__ import annotations

from .types import Ticket, TicketComment  # noqa: F401  (re-exported / type contract)


class JiraProvider:
    name = "jira"

    def __init__(self, config: dict):
        self.config = config
        self.workspace = config.get("workspace")
        self.default_project = config.get("default-project")
        self.mcp_tool_prefix = config.get("mcp-tool-prefix", "mcp__claude_ai_Atlassian")
        # TODO Phase 5: real connection via MCP server.
        # Atlassian MCP server exposes tools like `jira_fetch_ticket`,
        # `jira_search_issues`, `jira_add_comment` — connect via stdio bridge
        # or HTTP. Credentials from $ATLASSIAN_TOKEN env var (configured by
        # user; never persisted in workflow-config).

    def fetch_ticket(self, ticket_id: str) -> Ticket:
        # TODO Phase 5: call self.mcp_tool_prefix + "__jira_fetch_ticket"
        # with {workspace, ticket_id}; map JSON → normalized dict.
        raise NotImplementedError(
            f"JiraProvider.fetch_ticket({ticket_id!r}) — Phase 5 (MCP wiring pending)"
        )

    def list_tickets(self, filters: dict) -> list[Ticket]:
        # TODO Phase 5: translate `filters` into JQL; call MCP search tool.
        raise NotImplementedError("JiraProvider.list_tickets — Phase 5 (MCP wiring pending)")

    def post_comment(self, ticket_id: str, body: str) -> None:
        # TODO Phase 5: call MCP add_comment tool; gate behind
        # workflow-config.ticketing.post-back.require-confirmation.
        raise NotImplementedError(
            f"JiraProvider.post_comment({ticket_id!r}) — Phase 5 (MCP wiring pending)"
        )
