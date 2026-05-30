"""Common types for MCP providers.

Schema canônico de tickets normalizado entre Jira, Linear e GitHub Issues —
desacopla consumers do provider concreto. Cada provider deve mapear sua
representação interna para `Ticket` no `fetch_ticket`/`list_tickets`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Ticket:
    """Normalized ticket from any provider (Jira, Linear, GitHub Issues)."""

    id: str
    provider: str
    title: str
    body: str
    status: str
    priority: Optional[str] = None
    assignee: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class TicketComment:
    """Normalized comment on a ticket."""

    id: str
    ticket_id: str
    author: str
    body: str
    created_at: str
    raw: dict = field(default_factory=dict)


_STATUS_MAPPING: dict[str, dict[str, str]] = {
    "jira": {
        "To Do": "open",
        "Open": "open",
        "Backlog": "open",
        "In Progress": "in-progress",
        "In Review": "in-progress",
        "Code Review": "in-progress",
        "Done": "resolved",
        "Resolved": "resolved",
        "Closed": "closed",
        "Cancelled": "closed",
        "Canceled": "closed",
    },
    "linear": {
        "Backlog": "open",
        "Todo": "open",
        "Triage": "open",
        "In Progress": "in-progress",
        "In Review": "in-progress",
        "Done": "resolved",
        "Completed": "resolved",
        "Canceled": "closed",
        "Duplicate": "closed",
    },
    "github-issues": {
        "open": "open",
        "closed": "closed",
    },
}


def normalize_status(provider: str, raw_status: str) -> str:
    """Map provider-specific status names to canonical set.

    Canonical values: 'open' | 'in-progress' | 'resolved' | 'closed' | 'unknown'.
    """
    return _STATUS_MAPPING.get(provider, {}).get(raw_status, "unknown")
