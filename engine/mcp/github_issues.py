"""GitHub Issues ticketing provider — wrapper around `gh` CLI or GitHub MCP."""

from __future__ import annotations

from .types import Ticket, TicketComment  # noqa: F401  (re-exported / type contract)


class GitHubIssuesProvider:
    name = "github-issues"

    def __init__(self, config: dict):
        self.config = config
        self.workspace = config.get("workspace")  # e.g. "owner/repo"
        self.default_project = config.get("default-project")
        self.mcp_tool_prefix = config.get("mcp-tool-prefix", "mcp__github")
        # TODO Phase 5: real connection — prefer GitHub MCP server when
        # available; fall back to `gh issue view/list/comment` CLI calls.
        # Credentials: `gh auth status` (PAT or GH OAuth), no secrets stored
        # in workflow-config.

    def fetch_ticket(self, ticket_id: str) -> Ticket:
        # TODO Phase 5: `gh issue view {ticket_id} --json ...` or MCP equivalent.
        raise NotImplementedError(
            f"GitHubIssuesProvider.fetch_ticket({ticket_id!r}) — Phase 5 (MCP wiring pending)"
        )

    def list_tickets(self, filters: dict) -> list[Ticket]:
        # TODO Phase 5: translate filters into `gh issue list` flags.
        raise NotImplementedError(
            "GitHubIssuesProvider.list_tickets — Phase 5 (MCP wiring pending)"
        )

    def post_comment(self, ticket_id: str, body: str) -> None:
        # TODO Phase 5: `gh issue comment {ticket_id} --body ...`.
        raise NotImplementedError(
            f"GitHubIssuesProvider.post_comment({ticket_id!r}) — Phase 5 (MCP wiring pending)"
        )
