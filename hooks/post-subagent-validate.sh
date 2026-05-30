#!/usr/bin/env bash
# feature-forge — post-subagent-validate hook (Claude Code SubagentStop)
# Fires after a sub-agent (Task tool) completes. Validates outputs against
# the active task contract (if any). Forward-compat: engine may not yet
# route this event — `forge ingest` will silently ignore unknown events.
#
# Contract:
#   - Always exits 0
#   - All real work delegated to `forge ingest --event post-subagent-validate`
#
# Env:
#   CLAUDE_SUBAGENT_TYPE — type/name of the subagent that just stopped
#   CLAUDE_TASK_ID       — current task id (TASK-NNNN), if known
#   FORGE_BIN            — override forge binary path (default: "forge")
set -euo pipefail

SUBAGENT_TYPE="${CLAUDE_SUBAGENT_TYPE:-${1:-}}"
TASK_ID="${CLAUDE_TASK_ID:-${2:-}}"

if [[ -z "$SUBAGENT_TYPE" ]]; then
    exit 0
fi

FORGE_BIN="${FORGE_BIN:-forge}"
"$FORGE_BIN" ingest --event post-subagent-validate \
    --subagent "$SUBAGENT_TYPE" \
    --task-id "$TASK_ID" >/dev/null 2>&1 || true
exit 0
