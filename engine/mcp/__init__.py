"""MCP wrappers — Jira, Linear, GitHub Issues, Context7.

v1: interface stubs. Conexões reais (Phase 5) dependem de credentials no
.claude/workflow-config.yaml.ticketing e variáveis de ambiente.
"""

from .registry import get_ticketing_provider, get_docs_provider
from .types import Ticket, TicketComment, normalize_status

__all__ = [
    "get_ticketing_provider",
    "get_docs_provider",
    "Ticket",
    "TicketComment",
    "normalize_status",
]
