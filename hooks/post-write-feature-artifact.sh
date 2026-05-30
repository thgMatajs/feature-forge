#!/usr/bin/env bash
# feature-forge — post-write feature artifact hook (Claude Code)
# Fires when a feature artifact (intake, prd, tech-spec, task-contract, etc)
# is written under {features_root}/{slug}/{artifact}.{md|yaml|json}. Appends
# L1 history entry and updates the graph if the file is code.
#
# Contract:
#   - Never blocks the editor (always exits 0)
#   - Pattern-matches the path; if it doesn't look like a feature artifact, no-op
#   - All real work delegated to `forge ingest --event post-write-feature-artifact`
#
# Env:
#   CLAUDE_EDITED_FILE — path of the written file (Claude Code injects)
#   FORGE_BIN          — override forge binary path (default: "forge")
set -euo pipefail

FILE="${CLAUDE_EDITED_FILE:-${1:-}}"
[[ -z "$FILE" ]] && exit 0

FORGE_BIN="${FORGE_BIN:-forge}"

if [[ "$FILE" =~ /features/([^/]+)/([^/]+)\.(md|yaml|yml|json)$ ]]; then
    SLUG="${BASH_REMATCH[1]}"
    ARTIFACT="${BASH_REMATCH[2]}"
    "$FORGE_BIN" ingest --event post-write-feature-artifact \
        --feature-slug "$SLUG" \
        --artifact "$ARTIFACT" \
        --file "$FILE" >/dev/null 2>&1 || true
fi
exit 0
