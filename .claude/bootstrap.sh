#!/usr/bin/env bash
# feature-forge — one-time bootstrap pra rodar Claude Code com hooks/rules.
# Idempotente: pode rodar várias vezes sem efeito colateral.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

echo "🔨 feature-forge bootstrap"

# 1. Garante .claude/state/ existe com .gitkeep
mkdir -p .claude/state
[[ -f .claude/state/.gitkeep ]] || touch .claude/state/.gitkeep
echo "  ✓ .claude/state/ pronto"

# 1.5. Lock pra evitar race em runs simultâneos (codereviewbot PR #16 finding
# bootstrap.sh:46). flock é padrão Linux mas ausente em macOS por default —
# se não estiver disponível, segue sem lock (best-effort; race é raro porque
# `bash .claude/bootstrap.sh` é gesto manual one-shot).
LOCK_FILE=".claude/state/bootstrap.lock"
if command -v flock >/dev/null 2>&1; then
    exec 200>"$LOCK_FILE"
    if ! flock -n 200; then
        echo "  [bootstrap] Outra instância em curso (lock $LOCK_FILE) — aborta"
        exit 1
    fi
else
    # macOS default: sem flock; segue. Documentado como limite conhecido.
    echo "  [info] flock indisponível — bootstrap sem lock (ok em uso single-run típico)"
fi

# 2. Linka git hooks aos delegators canônicos em hooks/
# Glob `hooks/git-*` pega TODOS os delegators presentes — futuros hooks (ex.:
# `hooks/git-post-commit`) entram automaticamente sem editar este script
# (PR #16 finding T-N-016).
#
# Em worktrees Git, `.git` é arquivo apontando pra `.git/worktrees/<name>/`,
# e o subdir `hooks/` não é criado automaticamente nesse path. Resolve o
# caminho canônico via `git rev-parse --git-path hooks` (funciona tanto no
# .git/ tradicional quanto no gitdir do worktree) e garante mkdir.
GIT_HOOKS_DIR="$(git rev-parse --git-path hooks 2>/dev/null || echo "")"
if [[ -n "$GIT_HOOKS_DIR" ]]; then
    mkdir -p "$GIT_HOOKS_DIR"
else
    # Fallback defensivo: fora de repo git, mantém o path histórico.
    GIT_HOOKS_DIR=".git/hooks"
fi

for hook_source in hooks/git-*; do
    [[ -f "$hook_source" ]] || continue
    h="${hook_source#hooks/git-}"
    [[ -d "$GIT_HOOKS_DIR" ]] || { echo "  [skip] $GIT_HOOKS_DIR não acessível"; continue; }
    target="$GIT_HOOKS_DIR/$h"
    source_file="$hook_source"
    # hotfix-2: escolhe forma do symlink target conforme topologia do .git.
    # Em repo tradicional (`.git/` é diretório) o GIT_HOOKS_DIR é `.git/hooks`
    # e a forma relativa "../../hooks/git-X" resolve corretamente — preserva
    # contrato testado em test_bootstrap_symlink_handling.py (readlink ==
    # "../../hooks/git-pre-commit"). Em worktree (`.git` é arquivo apontando
    # pra `.git/worktrees/<n>/`), o GIT_HOOKS_DIR vive em
    # `.git/worktrees/<n>/hooks/` e "../../..." não resolve — usa absoluto.
    if [[ -d .git ]]; then
        expected="../../$source_file"
        expected_legacy="$REPO_ROOT/$source_file"
    else
        expected="$REPO_ROOT/$source_file"
        expected_legacy="../../$source_file"
    fi
    if [[ -f "$source_file" ]]; then
        if [[ -L "$target" || -f "$target" ]]; then
            current=$(readlink "$target" 2>/dev/null || echo "")
            # R3.2 fix: `[[ -L "$target" ]]` is true even when the symlink
            # target doesn't exist (broken link). Combine -L with -e (target
            # exists) so a broken symlink falls through to relink instead
            # of being silently accepted.
            if [[ "$current" == "$expected" && -e "$target" ]]; then
                echo "  ✓ $target → $source_file (já linkado)"
                continue
            elif [[ "$current" == "$expected_legacy" && -e "$target" ]]; then
                # Symlink legado (relativo) ainda válido — preserva idempotência.
                echo "  ✓ $target → $source_file (já linkado, forma legada)"
                continue
            elif [[ ( "$current" == "$expected" || "$current" == "$expected_legacy" ) && ! -e "$target" ]]; then
                # Symlink aponta pro lugar certo mas o alvo sumiu — relinka.
                echo "  [bootstrap] $target era symlink quebrado — recriando"
                rm -f "$target"
                # fall through to ln -s below
            elif [[ -n "$current" && "$current" != "$expected" && "$current" != "$expected_legacy" ]]; then
                echo "  [aviso] $target já existe e aponta pra outro lugar — pulando (revisão manual)"
                continue
            else
                # Arquivo regular existente, não symlink — pula com aviso
                echo "  [aviso] $target é arquivo regular — pulando (mova manualmente se quiser usar nosso delegator)"
                continue
            fi
        fi
        ln -s "$expected" "$target"
        chmod +x "$source_file" 2>/dev/null || true
        echo "  ✓ $target → $source_file (novo symlink)"
    else
        echo "  [skip] $source_file não existe — pulando (sem delegator pra linkar)"
    fi
done

# 3. Marca .claude/hooks/*.sh executáveis
if [[ -d .claude/hooks ]]; then
    chmod +x .claude/hooks/*.sh 2>/dev/null || true
    echo "  ✓ .claude/hooks/*.sh executáveis"
fi

# 4. Aviso sobre settings.local.json tracked
if git ls-files --error-unmatch .claude/settings.local.json >/dev/null 2>&1; then
    echo ""
    echo "  [aviso] .claude/settings.local.json está tracked. Recomendado untrack:"
    echo "       git rm --cached .claude/settings.local.json"
    echo "       (mantém o arquivo localmente, remove do git)"
    echo ""
fi

# 5. Install runtime deps + project em editable mode.
# pathspec (M-07) + pyyaml + project itself. Idempotente — se já instalado, no-op.
# Sem isto, `pytest --collect-only` quebra com ModuleNotFoundError em 38 arquivos.
# Captura stderr em log pra falha não ficar invisível (PR #16 finding
# codereviewbot bootstrap.sh:74 + T-N-015).
if command -v pip >/dev/null 2>&1; then
    _PIP_LOG=".claude/state/pip-install.log"
    if pip install -e . >"$_PIP_LOG" 2>&1 \
        || python3 -m pip install -e . >>"$_PIP_LOG" 2>&1; then
        echo "  ✓ runtime deps instaladas (pip install -e .)"
    else
        echo "  [aviso] 'pip install -e .' falhou — log em $_PIP_LOG"
        echo "         rode manualmente pra habilitar pathspec/mypy"
        echo "         últimas linhas:"
        tail -20 "$_PIP_LOG" >&2 || true
    fi
fi

# 6. Build inicial do graph + inventory (one-shot pós-clone).
# Idempotente. Sem isto, primeira invocação `forge graph` triggera lazy
# rebuild (~30s-2min — gerenciado por engine/graph_cli._maybe_auto_build).
#
# Deviation per plan Task 9.5.1 §"Pré-requisito de subcommand" caminho (b):
# `forge graph build --quiet` e `forge reconfigure --inventory-only` NÃO
# existem como subcommands non-interactive em v1.2-dev (engine/graph_cli.py
# é read-only; engine/reconfigure.py ignora argv per Decision 10). O fluxo
# canônico de build inicial é o lazy auto-build no próprio `forge graph`
# — bootstrap apenas avisa o usuário e disparara o lazy build via probe.
if command -v forge >/dev/null 2>&1; then
    echo "  [build] Preparando graph inicial (lazy build na primeira query, ~30s-2min)..."
    # Probe que dispara o auto-build. stdout suprimido pra não vazar JSON;
    # stderr capturado em log pra falha real não ficar invisível (PR #16
    # finding T-N-014). Se o usuário ainda não rodou `forge init`, é
    # esperado falhar — caminho corrente é informar e seguir.
    _GRAPH_LOG=".claude/state/bootstrap-graph.log"
    if forge graph --json q3 >/dev/null 2>"$_GRAPH_LOG"; then
        echo "  ✓ graph.db pronto"
    else
        echo "  [aviso] Build inicial do graph falhou — log em $_GRAPH_LOG"
        echo "         execute 'forge doctor' pra diagnóstico (ou 'forge init' se ainda não rodou)"
    fi
fi

echo "✅ Bootstrap completo. Próxima sessão Claude Code carrega hooks + rules automaticamente."
