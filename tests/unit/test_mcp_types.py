"""Unit tests — engine.mcp.types and engine.mcp.registry.

Validates the canonical status normaliser and the registry resolver, which
must return None when the provider block is absent / explicitly disabled.
"""

from __future__ import annotations

import pytest

from engine.mcp import registry, types


def test_normalize_status_jira():
    assert types.normalize_status("jira", "To Do") == "open"
    assert types.normalize_status("jira", "In Progress") == "in-progress"
    assert types.normalize_status("jira", "Done") == "resolved"
    assert types.normalize_status("jira", "Closed") == "closed"


def test_normalize_status_linear():
    assert types.normalize_status("linear", "Triage") == "open"
    assert types.normalize_status("linear", "Completed") == "resolved"
    assert types.normalize_status("linear", "Canceled") == "closed"


def test_normalize_status_github():
    assert types.normalize_status("github-issues", "open") == "open"
    assert types.normalize_status("github-issues", "closed") == "closed"


def test_normalize_status_unknown_provider():
    assert types.normalize_status("fictional", "anything") == "unknown"


def test_normalize_status_unknown_status_value():
    assert types.normalize_status("jira", "Made Up State") == "unknown"


def test_ticket_dataclass_defaults():
    t = types.Ticket(
        id="BONSAI-1",
        provider="jira",
        title="Sample",
        body="body",
        status="open",
    )
    assert t.labels == []
    assert t.assignee is None
    assert t.raw == {}


def test_ticket_comment_dataclass():
    c = types.TicketComment(
        id="c1",
        ticket_id="t1",
        author="alice",
        body="hi",
        created_at="2026-01-01T00:00:00Z",
    )
    assert c.raw == {}


def test_get_ticketing_provider_returns_none_when_absent():
    assert registry.get_ticketing_provider({}) is None


def test_get_ticketing_provider_returns_none_when_disabled():
    cfg = {"ticketing": {"provider": "none"}}
    assert registry.get_ticketing_provider(cfg) is None


def test_get_ticketing_provider_unknown_returns_none():
    cfg = {"ticketing": {"provider": "fictional-tracker"}}
    assert registry.get_ticketing_provider(cfg) is None


def test_get_docs_provider_returns_none_when_absent():
    assert registry.get_docs_provider({}) is None


def test_get_docs_provider_unknown_returns_none():
    cfg = {"external-docs": {"primary-provider": "fictional-docs"}}
    assert registry.get_docs_provider(cfg) is None
