#!/usr/bin/env bash
# feature-forge — PostToolUse hook (Edit|Write|NotebookEdit)
# Reminds about doc-sync when paths "vivos" são editados. Once per file
# per session — evita spam.
#
# Input: JSON via stdin (tool_input.file_path).
# Contract: exit 0 sempre.
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$PROJECT_ROOT/.claude/state"
WARNED="$STATE_DIR/drift-warned.json"
PENDING="$STATE_DIR/drift-pending.json"

mkdir -p "$STATE_DIR"

INPUT="$(cat 2>/dev/null || true)"
[[ -z "$INPUT" ]] && exit 0

FILE_PATH=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" <<< "$INPUT")

[[ -z "$FILE_PATH" ]] && exit 0

REL_PATH="${FILE_PATH#$PROJECT_ROOT/}"

# Match paths "vivos"
is_live_code() {
    case "$1" in
        engine/*|validators/*|hooks/*|templates/*|cards/*|presets/*|docs/schemas/*)
            return 0 ;;
        *) return 1 ;;
    esac
}

if ! is_live_code "$REL_PATH"; then
    exit 0
fi

# Check se já avisou nesta sessão
ALREADY_WARNED=$(WARNED="$WARNED" TARGET="$REL_PATH" python3 -c "
import json, sys, os
path = os.environ.get('WARNED', '')
target = os.environ.get('TARGET', '')
if not os.path.exists(path):
    print('no')
    sys.exit(0)
try:
    with open(path) as f:
        data = json.load(f)
    if target in data.get('files', []):
        print('yes')
    else:
        print('no')
except Exception:
    print('no')
")

if [[ "$ALREADY_WARNED" == "yes" ]]; then
    exit 0
fi

# Append to warned + pending — protected by fcntl.flock so concurrent
# hook invocations (Edit/Write/NotebookEdit in parallel) can't race on
# the read-modify-write of the JSON state files. R3.3 fix. We do the
# lock inside python3 (fcntl.flock) because the system `flock(1)`
# binary isn't present on stock macOS — python's stdlib gives us the
# same primitive cross-platform.
WARNED="$WARNED" PENDING="$PENDING" TARGET="$REL_PATH" \
    STATE_DIR="$STATE_DIR" python3 -c "
import fcntl, json, os, sys

warned_path = os.environ['WARNED']
pending_path = os.environ['PENDING']
target = os.environ['TARGET']
state_dir = os.environ['STATE_DIR']

lock_path = os.path.join(state_dir, '.drift-state.lock')
with open(lock_path, 'w') as lock_fh:
    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
    try:
        for p in (warned_path, pending_path):
            data = {'files': []}
            if os.path.exists(p):
                try:
                    with open(p) as f:
                        data = json.load(f)
                except Exception:
                    data = {'files': []}
            if target not in data.get('files', []):
                data.setdefault('files', []).append(target)
            with open(p, 'w') as f:
                json.dump(data, f, indent=2)
    finally:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
"

cat <<EOF >&2

📝 doc-drift: $REL_PATH editado.

Doc-sync per-commit (mesmo commit):
  · CHANGELOG.md (Unreleased)
  · README.md (se stats mudaram)

Fim de sessão (não per-commit): rode \`.claude/bin/mem session\` pra
registrar o handoff curado (estado + próximos passos; git_meta automático).
O docs/design/08-session-handoff.md NÃO é mais editado a cada sessão —
congelou como snapshot histórico + fallback de bootstrap.

Matriz completa: .claude/rules/doc-sync.md

EOF

exit 0
