#!/usr/bin/env bash
# feature-forge — SessionStart hook (Claude Code)
# Injects orientation at session start so orchestrator has Mandamento 0
# fresh and current state without having to re-read all docs.
#
# Contract:
#   - Always exits 0
#   - Stdout is injected as additional context
#   - Stderr is logged but not blocking
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$PROJECT_ROOT/.claude/state"
HANDOFF="$PROJECT_ROOT/docs/design/08-session-handoff.md"

# Reset per-session state
rm -f "$STATE_DIR/drift-warned.json" 2>/dev/null || true

# Extract handoff metadata
UPDATED="(handoff missing)"
STATE_LINE="(handoff missing)"
if [[ -f "$HANDOFF" ]]; then
    UPDATED=$(grep -m1 '^\*\*Última atualização:\*\*' "$HANDOFF" \
        | sed 's/^\*\*Última atualização:\*\* //' || echo "(unknown)")
    STATE_LINE=$(grep -m1 '^\*\*Estado:\*\*' "$HANDOFF" \
        | sed 's/^\*\*Estado:\*\* //' || echo "(unknown)")
fi

# Check drift from previous session
DRIFT_PENDING="não"
if [[ -f "$STATE_DIR/drift-pending.json" && -s "$STATE_DIR/drift-pending.json" ]]; then
    DRIFT_PENDING="sim"
fi

cat <<EOF
🔨 feature-forge — orientação de sessão

Você é o ORQUESTRADOR-MANTENEDOR. Nunca Write/Edit/NotebookEdit/Bash-mutação
direto — toda mudança é despachada via Agent tool (gsd-executor / gsd-code-
reviewer / gsd-code-fixer).

Estado do projeto:
  · Última atualização handoff: $UPDATED
  · Estado: $STATE_LINE
  · Drift pendente da sessão anterior: $DRIFT_PENDING

Antes de qualquer trabalho:
  1. Brainstorm com usuário → writing-plans
  2. Dispatch gsd-executor (impl) → gsd-code-reviewer (review) → gsd-code-fixer (fixes)
  3. Verification → doc-sync → commit

Regras: CLAUDE.md · Mandamento 0: .claude/rules/orchestrator-persona.md
EOF

exit 0
