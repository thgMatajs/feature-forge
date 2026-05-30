#!/usr/bin/env bash
# feature-forge — session-start drift check (Claude Code SessionStart)
# Fires when a Claude Code session begins. Compares card snapshot sha256s
# against the canonical workflow-config to detect drift. Warnings go to
# stderr — the session always starts.
#
# Contract:
#   - Always exits 0
#   - Skips silently on non-forge projects (no .claude/ dir)
#   - All real work delegated to `forge ingest --event session-start`
#
# Env:
#   FORGE_BIN — override forge binary path (default: "forge")
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [[ ! -d "$PROJECT_ROOT/.claude" ]]; then
    exit 0
fi

FORGE_BIN="${FORGE_BIN:-forge}"
"$FORGE_BIN" ingest --event session-start \
    --project-root "$PROJECT_ROOT" >/dev/null 2>&1 || true
exit 0
