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
MEM_DIR="$PROJECT_ROOT/.claude/memory"

# Reset per-session state
rm -f "$STATE_DIR/drift-warned.json" 2>/dev/null || true

# ── Session state: lê nota `session` mais recente diretamente do JSONL ──
# Contrato exit-0 (R3.5): o hook NÃO usa `set -e`; toda etapa abaixo
# degrada graciosamente (sem JSONL → fallback grep → "(handoff missing)").
#
# Por que JSONL em vez de `mem find/get`:
#   `mem find` ranqueia por SCORE (importância × decay × recall_count), NÃO
#   por data de criação. `mem get` infla o recall_count da nota acessada a
#   cada sessão → a PRIMEIRA nota `session` lida fica pinada no topo do
#   `-k 1` para sempre; a nota genuinamente mais recente nunca é injetada.
#   Ler o JSONL committed diretamente evita ambos os problemas e funciona
#   mesmo sem mem.db (clone fresco antes do rebuild).
MEM_BODY=""
if [[ -d "$MEM_DIR" ]]; then
    MEM_BODY=$(python3 - "$MEM_DIR" <<'PYEOF' 2>/dev/null
import json, os, sys, glob

mem_dir = sys.argv[1]
try:
    # Passo 1: coleta todos os snapshots de todos os arquivos .jsonl,
    # ordenados por (nome-do-arquivo, posição-da-linha) — mesma ordem
    # que o mem usa no event-sourcing (last-write-wins por id).
    snapshots = []
    for jsonl_path in sorted(glob.glob(os.path.join(mem_dir, "*.jsonl"))):
        with open(jsonl_path, encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    snapshots.append((jsonl_path, lineno, json.loads(raw)))
                except Exception:
                    pass  # linha malformada — ignora

    # Passo 2: last-write-wins por id (mantém o snapshot mais recente na
    # ordem de leitura — arquivo alfabético + posição de linha).
    latest_by_id = {}
    for path, lineno, obj in snapshots:
        oid = obj.get("id")
        if oid:
            latest_by_id[oid] = obj

    # Passo 3: filtra type == "session" E status == "active".
    sessions = [
        obj for obj in latest_by_id.values()
        if obj.get("type") == "session" and obj.get("status") == "active"
    ]

    if not sessions:
        print("")
    else:
        # Passo 4: maior created_at (ISO-8601 Z → comparação lexicográfica ok).
        #
        # Resiliência (cross-AI bot PR#32): este hook é o caminho de
        # continuidade entre sessões — escolher a sessão errada surfa o
        # handoff errado no SessionStart. O JSONL é editável à mão, então
        # um `created_at` corrompido (não-ISO) ou ausente NÃO pode quebrar
        # nem mis-ordenar a seleção. A chave de ordenação valida que o
        # valor é uma string ISO parseável ANTES de usá-lo; entradas com
        # `created_at` ausente OU malformado caem pra um sentinela vazio
        # ("") que as ordena pro FIM — nunca são escolhidas como "mais
        # recente". O caso feliz (datas ISO válidas) mantém o comportamento
        # atual: comparação lexicográfica direta da string ISO-8601 Z.
        from datetime import datetime

        def created_at_key(o):
            raw = o.get("created_at")
            if not isinstance(raw, str) or not raw:
                return ""  # ausente / não-string → ordena pro fim
            try:
                # Normaliza o sufixo Z (ISO-8601 UTC), que fromisoformat só
                # aceita a partir do 3.11; valida que é uma data parseável.
                datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return ""  # malformado ("abc", lixo) → ordena pro fim
            return raw  # ISO válido → comparação lexicográfica (caso feliz)

        newest = max(sessions, key=created_at_key)
        print(newest.get("body", "").strip())
except Exception:
    print("")
PYEOF
)
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
