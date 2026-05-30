"""Context7 docs provider — version-aware library documentation lookups."""

from __future__ import annotations

from typing import Optional


class Context7Provider:
    name = "context7"

    def __init__(self, config: dict):
        self.config = config
        self.mcp_tool_prefix = config.get("mcp-tool-prefix", "mcp__context7")
        self.cache_ttl_days = (config.get("cache-ttl-days") or {})
        self.privacy_mode = bool(config.get("privacy-mode", False))
        # TODO Phase 5: connect to Context7 MCP. Usually local-hosted; no
        # secret needed. URL configured in workflow-config.external-docs.
        # When privacy_mode is True, the provider MUST refuse to send raw
        # project names/code to the MCP — only generic library IDs.

    def lookup_lib(self, lib_name: str, *, version: Optional[str] = None) -> dict:
        # TODO Phase 5: call `resolve-library-id` MCP tool.
        raise NotImplementedError(
            f"Context7Provider.lookup_lib({lib_name!r}, version={version!r}) — Phase 5"
        )

    def query(self, lib_name: str, query: str) -> str:
        # TODO Phase 5: call `query-docs` MCP tool with resolved lib id.
        raise NotImplementedError(
            f"Context7Provider.query({lib_name!r}, ...) — Phase 5 (MCP wiring pending)"
        )
