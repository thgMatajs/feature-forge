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

# 2. Linka git hooks aos delegators canônicos em hooks/
for h in pre-commit pre-push; do
    target=".git/hooks/$h"
    source_file="hooks/git-$h"
    if [[ -f "$source_file" ]]; then
        if [[ -L "$target" || -f "$target" ]]; then
            current=$(readlink "$target" 2>/dev/null || echo "")
            expected="../../$source_file"
            # R3.2 fix: `[[ -L "$target" ]]` is true even when the symlink
            # target doesn't exist (broken link). Combine -L with -e (target
            # exists) so a broken symlink falls through to relink instead
            # of being silently accepted.
            if [[ "$current" == "$expected" && -e "$target" ]]; then
                echo "  ✓ $target → $source_file (já linkado)"
                continue
            elif [[ "$current" == "$expected" && ! -e "$target" ]]; then
                # Symlink aponta pro lugar certo mas o alvo sumiu — relinka.
                echo "  ⚙️  $target era symlink quebrado — recriando"
                rm -f "$target"
                # fall through to ln -s below
            elif [[ -n "$current" && "$current" != "$expected" ]]; then
                echo "  ⚠️  $target já existe e aponta pra outro lugar — pulando (revisão manual)"
                continue
            else
                # Arquivo regular existente, não symlink — pula com aviso
                echo "  ⚠️  $target é arquivo regular — pulando (mova manualmente se quiser usar nosso delegator)"
                continue
            fi
        fi
        ln -s "../../$source_file" "$target"
        chmod +x "$source_file" 2>/dev/null || true
        echo "  ✓ $target → $source_file (novo symlink)"
    else
        echo "  ⊘ $source_file não existe — pulando (sem delegator pra linkar)"
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
    echo "  ⚠️  .claude/settings.local.json está tracked. Recomendado untrack:"
    echo "       git rm --cached .claude/settings.local.json"
    echo "       (mantém o arquivo localmente, remove do git)"
    echo ""
fi

echo "✅ Bootstrap completo. Próxima sessão Claude Code carrega hooks + rules automaticamente."
