"""Registry — resolve ticketing/docs providers from workflow-config.

Lê o bloco `ticketing` ou `external-docs` do workflow-config.yaml e
instancia o handler correto. Retorna None se o provider for `none`
ou se o bloco estiver ausente.

Os handlers concretos vivem em sibling modules (jira.py, linear.py,
github_issues.py, context7.py) e implementam os Protocols abaixo.
"""

from __future__ import annotations

import sys
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class TicketingProvider(Protocol):
    """Interface for external issue trackers (Jira, Linear, GitHub Issues).

    All methods are synchronous from the engine's perspective; the actual
    MCP transport (stdio/HTTP) may be async-under-the-hood — the wrapper
    blocks until the MCP call returns.
    """

    name: str

    def fetch_ticket(self, ticket_id: str) -> dict:
        """Fetch full ticket payload by ID (e.g. 'BONSAI-123').

        Returns a normalized dict with at least: id, title, description,
        status, acceptance_criteria, attachments, linked_tickets.
        """
        ...

    def list_tickets(self, filters: dict) -> list[dict]:
        """List tickets matching filters (e.g. sprint, assignee, status)."""
        ...

    def post_comment(self, ticket_id: str, body: str) -> None:
        """Post a comment back to the ticket. Used for readiness/done hooks."""
        ...


@runtime_checkable
class DocsProvider(Protocol):
    """Interface for version-aware library documentation lookups."""

    name: str

    def lookup_lib(self, lib_name: str, *, version: Optional[str] = None) -> dict:
        """Resolve a library name to a canonical doc identifier + metadata."""
        ...

    def query(self, lib_name: str, query: str) -> str:
        """Free-form natural-language query against the library's docs."""
        ...


_TICKETING_PROVIDERS = {
    "jira": ("engine.mcp.jira", "JiraProvider"),
    "linear": ("engine.mcp.linear", "LinearProvider"),
    "github-issues": ("engine.mcp.github_issues", "GitHubIssuesProvider"),
    "github_issues": ("engine.mcp.github_issues", "GitHubIssuesProvider"),
}

_DOCS_PROVIDERS = {
    "context7": ("engine.mcp.context7", "Context7Provider"),
}


def _instantiate(module_path: str, class_name: str, config: dict):
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(config)


def get_ticketing_provider(workflow_config: dict) -> Optional[TicketingProvider]:
    """Resolve the ticketing provider declared in workflow-config.

    Returns None when:
    - `ticketing` block is absent
    - `ticketing.provider` is `none` or empty
    - provider name is unknown (logs warning em stderr para o usuário
      detectar typos como 'jirra' em vez de 'jira')
    """
    ticketing = workflow_config.get("ticketing") or {}
    provider_name = ticketing.get("provider")
    if not provider_name or provider_name == "none":
        return None

    entry = _TICKETING_PROVIDERS.get(provider_name)
    if entry is None:
        # F7: warning em stderr — provider desconhecido geralmente é typo.
        known = sorted(_TICKETING_PROVIDERS.keys())
        print(
            f"forge: ticketing provider {provider_name!r} desconhecido. "
            f"Conhecidos: {known}",
            file=sys.stderr,
        )
        return None

    module_path, class_name = entry
    return _instantiate(module_path, class_name, ticketing)


def get_docs_provider(workflow_config: dict) -> Optional[DocsProvider]:
    """Resolve the docs provider declared in workflow-config.external-docs.

    Mesmo comportamento de warning para providers desconhecidos.
    """
    external_docs = workflow_config.get("external-docs") or {}
    provider_name = external_docs.get("primary-provider") or external_docs.get("provider")
    if not provider_name or provider_name == "none":
        return None

    entry = _DOCS_PROVIDERS.get(provider_name)
    if entry is None:
        # F7: warning em stderr — provider desconhecido geralmente é typo.
        known = sorted(_DOCS_PROVIDERS.keys())
        print(
            f"forge: docs provider {provider_name!r} desconhecido. "
            f"Conhecidos: {known}",
            file=sys.stderr,
        )
        return None

    module_path, class_name = entry
    return _instantiate(module_path, class_name, external_docs)
