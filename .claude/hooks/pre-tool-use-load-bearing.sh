#!/usr/bin/env bash
# feature-forge — PreToolUse hook (Edit|Write|NotebookEdit)
# Warns + audit logs when load-bearing files are about to be edited.
# Never blocks (per design: hooks leves + 1 hard-block apenas no
# pre-commit das decisions).
#
# Input: JSON via stdin com `tool_input.file_path` (Claude Code hook protocol).
# Contract: exit 0 sempre; stderr é mostrado mas não bloqueia.
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$PROJECT_ROOT/.claude/state"
AUDIT_LOG="$STATE_DIR/load-bearing-edits.jsonl"

mkdir -p "$STATE_DIR"

# Parse file_path do JSON stdin (defensivo — se input não é JSON válido, sai 0)
INPUT="$(cat 2>/dev/null || true)"
if [[ -z "$INPUT" ]]; then
    exit 0
fi

# Extract file_path com python (mais robusto que jq pra ambientes variados)
FILE_PATH=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" <<< "$INPUT")

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Path relativo ao repo (se foi passado absoluto)
REL_PATH="${FILE_PATH#$PROJECT_ROOT/}"

# Lista de patterns load-bearing
is_load_bearing() {
    case "$1" in
        docs/design/00-vision.md) return 0 ;;
        docs/design/01-decisions.md) return 0 ;;
        docs/design/05-filesystem-layout.md) return 0 ;;
        docs/design/06-command-surface.md) return 0 ;;
        docs/design/07-discipline.md) return 0 ;;
        docs/schemas/*) return 0 ;;
        presets/*) return 0 ;;
        cards/*) return 0 ;;
        CLAUDE.md) return 0 ;;
        .claude/rules/*) return 0 ;;
        *) return 1 ;;
    esac
}

if is_load_bearing "$REL_PATH"; then
    cat <<EOF >&2

🛑 LOAD-BEARING edit: $REL_PATH

Confirme intenção explícita. Se revisita decisão locked, commit deve
dizer "Revisita decisão N" no CHANGELOG (hard-block do pre-commit).

Detalhe: .claude/rules/scope.md + .claude/rules/decisions.md

EOF

    # Audit log
    TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    TOOL=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get('tool_name', 'unknown'))
except Exception:
    print('unknown')
" <<< "$INPUT")

    printf '{"ts":"%s","file":"%s","tool":"%s"}\n' \
        "$TS" "$REL_PATH" "$TOOL" >> "$AUDIT_LOG"
fi

exit 0
