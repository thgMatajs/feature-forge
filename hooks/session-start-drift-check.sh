#!/usr/bin/env bash
# feature-forge — session-start drift check (Claude Code SessionStart)
# Fires when a Claude Code session begins. Compares card snapshot sha256s
# against the canonical workflow-config to detect drift. Warnings go to
# stderr — the session always starts.
#
# Contract:
#   - Always exits 0
#   - Skips silently on non-forge projects (no .claude/ dir)
#   - All real work delegated to `forge ingest --event session-start`
#
# Env:
#   FORGE_BIN — override forge binary path (default: "forge")
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [[ ! -d "$PROJECT_ROOT/.claude" ]]; then
    exit 0
fi

FORGE_BIN="${FORGE_BIN:-forge}"
"$FORGE_BIN" ingest --event session-start \
    --project-root "$PROJECT_ROOT" >/dev/null 2>&1 || true

# ── Graph-first reminder (W-GRAPH Camada 2) ──────────────────────────────────
# Lembra o host que o graph.db está disponível e como consultá-lo. Self-contained
# no shell (aditivo, não colide com o renderer host-aware). Saída em stderr; a
# sessão sempre começa. Silencioso quando o grafo ainda não foi construído.
if [[ -f "$PROJECT_ROOT/.claude/graph.db" ]]; then
    # Host-aware: emoji só em TTY interativo fora do Claude Code; senão ASCII.
    if [[ -t 1 && -z "${CLAUDECODE:-}" ]]; then
        _g_prefix="🔎 graph"
    else
        _g_prefix="[graph]"
    fi
    {
        echo "$_g_prefix codebase graph disponível em .claude/graph.db — consulte antes de ler o source."
        echo "$_g_prefix queries: forge graph --json <q1 similar | q2 blast-radius | q3 orphans | q4 symbols | q8 di-deps>"
        echo "$_g_prefix referência completa: .claude/forge/graph-skill.md"
    } >&2
fi
exit 0
