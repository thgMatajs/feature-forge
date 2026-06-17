#!/usr/bin/env bash
# feature-forge — instalador curl-one-liner
#
# Uso canônico:
#   curl -fsSL https://raw.githubusercontent.com/thgMatajs/feature-forge/main/scripts/install.sh | bash
#
# O script:
#   1. Verifica pré-requisitos (git, python3 >= 3.11)
#   2. Define FORGE_HOME via XDG_DATA_HOME (~/.local/share/feature-forge por padrão)
#   3. Guard: aborta se FORGE_HOME já existe (sugere forge upgrade)
#   4. Clona o repositório em FORGE_HOME
#   5. Cria venv e instala dependências via pip install -e
#   6. Cria symlink em ~/.local/bin/forge
#   7. Smoke: forge --version
#
# Spec ref: §3 D.1
set -euo pipefail

# ── Pré-requisitos ────────────────────────────────────────────────────────────

command -v git >/dev/null 2>&1 || {
  echo "erro: git não encontrado. Instale git e tente novamente."
  exit 1
}

command -v python3 >/dev/null 2>&1 || {
  echo "erro: python3 não encontrado. Instale python3 >= 3.11 e tente novamente."
  exit 1
}

python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null || {
  PY_VER=$(python3 --version 2>&1)
  echo "erro: python3 >= 3.11 necessário. Versão encontrada: $PY_VER"
  exit 1
}

# ── Configuração ──────────────────────────────────────────────────────────────

FORGE_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/feature-forge"
FORGE_REPO_URL="https://github.com/thgMatajs/feature-forge.git"

# ── Aviso + grace period (abort via Ctrl+C) ───────────────────────────────────

echo ""
echo "🔨 feature-forge install em $FORGE_HOME"
echo "(abort com Ctrl+C nos próximos 3s se mudou de ideia)"
sleep 3

# ── Guard: FORGE_HOME já existe ───────────────────────────────────────────────

if [[ -d "$FORGE_HOME" ]]; then
  echo ""
  echo "erro: '$FORGE_HOME' já existe."
  echo "Se feature-forge já está instalado, rode 'forge upgrade' para atualizar."
  echo "Para reinstalar do zero, remova o diretório manualmente:"
  echo "  rm -rf \"$FORGE_HOME\""
  exit 1
fi

# ── Clone ─────────────────────────────────────────────────────────────────────

echo ""
echo "clonando feature-forge em $FORGE_HOME..."
git clone --depth=1 "$FORGE_REPO_URL" "$FORGE_HOME"

# ── Venv + dependências ───────────────────────────────────────────────────────

echo ""
echo "criando ambiente virtual..."
python3 -m venv "$FORGE_HOME/.venv"

echo "instalando dependências..."
"$FORGE_HOME/.venv/bin/pip" install --quiet -e "$FORGE_HOME"

# ── Symlink em ~/.local/bin ───────────────────────────────────────────────────

mkdir -p "$HOME/.local/bin"
ln -sf "$FORGE_HOME/bin/forge" "$HOME/.local/bin/forge"

# ── Smoke ─────────────────────────────────────────────────────────────────────

echo ""
if "$FORGE_HOME/bin/forge" --version >/dev/null 2>&1; then
  echo "✓ instalado. próximo: cd <projeto> && forge init"
else
  echo "aviso: instalação concluída mas smoke test falhou."
  echo "Tente: $FORGE_HOME/bin/forge --version"
fi
