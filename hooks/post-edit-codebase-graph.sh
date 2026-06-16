#!/usr/bin/env bash
# feature-forge — post-edit hook (Claude Code)
# Fires after Edit/Write/NotebookEdit tools. Updates the SQLite graph
# incrementally for code files (.kt, .kts, .swift, .ts, .tsx, .js, .jsx,
# .java, .xml, .m, .mm).
#
# Contract:
#   - Never blocks the editor (always exits 0)
#   - Filters early-exit on non-code files and non-forge projects
#   - All real work delegated to `forge ingest --event post-edit`
#
# Env:
#   CLAUDE_EDITED_FILE — path of the edited file (Claude Code injects this)
#   CLAUDE_TOOL        — Edit | Write | NotebookEdit (informational)
#   FORGE_BIN          — override forge binary path (default: "forge")
set -euo pipefail

FILE="${CLAUDE_EDITED_FILE:-${1:-}}"
if [[ -z "$FILE" ]]; then
    exit 0
fi

# Early-exit em paths gerados / dependency / artifact (PR #16 finding T-N-017).
# Sem isso, edits em build/ ou node_modules/ disparam re-ingest de arquivos
# que não pertencem ao codebase canônico — particularmente custoso pra `.m`
# falso-positivo em diretórios de output que casualmente terminem em `.m`
# (ex.: `*.map.m` ou source maps minificados). Match por substring evita
# loop sobre extensão.
case "$FILE" in
    */build/*|*/node_modules/*|*/.gradle/*|*/dist/*|*/target/*|*/DerivedData/*|*/.next/*|*/out/*)
        exit 0
        ;;
esac

case "$FILE" in
    *.kt|*.kts|*.swift|*.ts|*.tsx|*.js|*.jsx|*.java|*.xml|*.m|*.mm) ;;
    *) exit 0 ;;
esac

FORGE_BIN="${FORGE_BIN:-forge}"
"$FORGE_BIN" ingest --event post-edit --file "$FILE" >/dev/null 2>&1 || true
exit 0
