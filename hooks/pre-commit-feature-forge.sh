#!/usr/bin/env bash
# feature-forge — pre-commit hook (Claude Code + git delegate)
# Fires before `git commit`. Runs `forge verify` (scope inferred) in
# non-interactive mode. Warnings go to stderr, but the commit always
# proceeds — hooks must never block git.
#
# Contract:
#   - Always exits 0 (never blocks the commit)
#   - Skips silently on non-forge projects (no .claude/ dir)
#   - Engine decides scope (task vs feature) based on L1 state
#
# Env:
#   FORGE_BIN — override forge binary path (default: "forge")
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [[ ! -d "$PROJECT_ROOT/.claude" ]]; then
    exit 0
fi

FORGE_BIN="${FORGE_BIN:-forge}"
STAGED="$(git diff --cached --name-only 2>/dev/null | tr '\n' ',' || true)"

if ! "$FORGE_BIN" ingest --event pre-commit \
    --project-root "$PROJECT_ROOT" \
    --staged-files "$STAGED" >/dev/null 2>&1; then
    echo "feature-forge: verify reported issues — commit will proceed but flag risk" >&2
fi
exit 0
