#!/usr/bin/env bash
# feature-forge — git pre-commit (canonical, called by hooks/git-pre-commit).
# Two checks:
#   (1) HARD BLOCK: docs/design/01-decisions.md staged without "Revisita
#       decisão" in staged CHANGELOG.md → exit 1.
#   (2) SOFT WARNING: code "vivo" staged sem CHANGELOG/README staged.
#
# Override consciente: git commit --no-verify (registra bypass deliberado).
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$PROJECT_ROOT/.claude/state"

CHANGED=$(git diff --cached --name-only 2>/dev/null || true)
if [[ -z "$CHANGED" ]]; then
    exit 0
fi

# ─── HARD BLOCK: decisions sem ceremony ───────────────────────────────

TOUCHES_DECISIONS=$(echo "$CHANGED" | grep -E '^docs/design/01-decisions\.md$' || true)
if [[ -n "$TOUCHES_DECISIONS" ]]; then
    CHANGELOG_DIFF=$(git diff --cached CHANGELOG.md 2>/dev/null || true)
    if ! echo "$CHANGELOG_DIFF" | grep -qiE 'revisita decisão|revisit decision'; then
        cat <<'EOF' >&2

🛑 BLOCK: docs/design/01-decisions.md alterado sem cerimônia.

    Adicione entrada em CHANGELOG.md (staged) contendo:
      'Revisita decisão N: <novo choice> — <rationale>'

    Por quê: decisões locked são imutáveis sem revisitar (mandamento #1).
    Override consciente: git commit --no-verify (registra que foi deliberado).

    Detalhe: .claude/rules/decisions.md

EOF
        exit 1
    fi
fi

# ─── SOFT WARNING: doc-sync ausente ───────────────────────────────────

TOUCHED_CODE=$(echo "$CHANGED" | grep -E '^(engine|validators|hooks|templates|cards|presets|docs/schemas)/' || true)
if [[ -n "$TOUCHED_CODE" ]]; then
    TOUCHED_DOCS=$(echo "$CHANGED" | grep -E '^(CHANGELOG\.md|README\.md)$' || true)
    if [[ -z "$TOUCHED_DOCS" ]]; then
        cat <<EOF >&2

⚠️  doc-sync: commit toca código vivo mas não CHANGELOG/README.

    Arquivos vivos alterados:
$(echo "$TOUCHED_CODE" | sed 's/^/      · /')

    Lembre-se de atualizar doc-sync (CHANGELOG/README) ou justifique no
    commit body. O handoff de sessão não é per-commit: rode
    \`.claude/bin/mem session\` no fim da sessão. (Sem bloqueio — só aviso.)

EOF
    fi
fi

# Limpa drift-pending consumido pelo commit
rm -f "$STATE_DIR/drift-pending.json" 2>/dev/null || true

exit 0
