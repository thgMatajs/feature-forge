#!/usr/bin/env bash
# feature-forge — SessionStart hook (Claude Code)
# Injects orientation at session start so orchestrator has Mandamento 0
# fresh and current state without having to re-read all docs.
#
# Contract:
#   - Always exits 0
#   - Stdout is injected as additional context
#   - Stderr is logged but not blocking
#
# R3.5 fix: do NOT use `set -euo pipefail`. The contract above promises
# exit 0 in all conditions, but `set -e` would cause any sub-command
# failure (missing handoff file, grep returning empty, etc.) to abort
# the script with non-zero. The script falls back gracefully on each
# step (|| echo "(unknown)"), so we want errors to *propagate to
# stderr* but NOT terminate the script. Explicit `exit 0` at the end
# guarantees the contract.

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$PROJECT_ROOT/.claude/state"
HANDOFF="$PROJECT_ROOT/docs/design/08-session-handoff.md"
MEM_BIN="$PROJECT_ROOT/.claude/bin/mem"

# Reset per-session state
rm -f "$STATE_DIR/drift-warned.json" 2>/dev/null || true

# ── Session state: tenta o último `mem session`, fallback pro arquivo ──
# Contrato exit-0 (R3.5): o hook NÃO usa `set -e`; toda etapa abaixo
# degrada graciosamente (mem ausente → fallback grep → "(handoff missing)").
MEM_BODY=""
if [[ -x "$MEM_BIN" ]]; then
    # Passo 1: id da última `mem session` (score-ordered; a mais recente
    # decai menos → maior score → topo de `-k 1`). `[]` quando não há
    # sessão → SID vazio → cai no fallback. Stderr do mem é descartado.
    #
    # Timeout portátil (L-001): `timeout` não é built-in no macOS. Como
    # python3 já é dep dura do projeto, usamos subprocess.run(timeout=5)
    # pra bound ambas as chamadas ao mem. Se o teto estourar (ou o mem
    # retornar erro), retornamos string vazia → cai no fallback do arquivo.
    SID=$(python3 - "$MEM_BIN" <<'PYEOF' 2>/dev/null
import json, subprocess, sys
mem_bin = sys.argv[1]
try:
    r = subprocess.run(
        [mem_bin, "--json", "find", "", "--type", "session", "-k", "1"],
        capture_output=True, text=True, timeout=5
    )
    data = json.loads(r.stdout) if r.returncode == 0 else []
    print(data[0]["id"] if data else "")
except Exception:
    print("")
PYEOF
)
    # Passo 2: corpo do handoff curado (.body). `get` registra access — é
    # uma leitura real, comportamento esperado (igual à skill mem-resume).
    if [[ -n "$SID" ]]; then
        MEM_BODY=$(python3 - "$MEM_BIN" "$SID" <<'PYEOF' 2>/dev/null
import json, subprocess, sys
mem_bin, sid = sys.argv[1], sys.argv[2]
try:
    r = subprocess.run(
        [mem_bin, "--json", "get", sid],
        capture_output=True, text=True, timeout=5
    )
    body = json.loads(r.stdout).get("body", "").strip() if r.returncode == 0 else ""
    print(body)
except Exception:
    print("")
PYEOF
)
    fi
fi

# Fallback pro arquivo (clone fresco antes do mem rebuild, ou repo sem
# nenhum `mem session` ainda, ou qualquer falha do mem acima).
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

# Monta a seção de estado: corpo do mem (preferido) ou os 2 campos do arquivo.
if [[ -n "$MEM_BODY" ]]; then
    STATE_BLOCK="Estado do projeto (último \`mem session\`):

$MEM_BODY

  · Drift pendente da sessão anterior: $DRIFT_PENDING"
else
    STATE_BLOCK="Estado do projeto (fallback: docs/design/08-session-handoff.md):
  · Última atualização handoff: $UPDATED
  · Estado: $STATE_LINE
  · Drift pendente da sessão anterior: $DRIFT_PENDING"
fi

cat <<EOF
🔨 feature-forge — orientação de sessão

Você é o ORQUESTRADOR-MANTENEDOR. Nunca Write/Edit/NotebookEdit/Bash-mutação
direto — toda mudança é despachada via Agent tool (gsd-executor / gsd-code-
reviewer / gsd-code-fixer).

$STATE_BLOCK

Antes de qualquer trabalho:
  1. Brainstorm com usuário → writing-plans
  2. Dispatch gsd-executor (impl) → gsd-code-reviewer (review) → gsd-code-fixer (fixes)
  3. Verification → doc-sync → commit

Regras: CLAUDE.md · Mandamento 0: .claude/rules/orchestrator-persona.md
EOF

exit 0
