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
#   4. Descobre a última release tag (v*) no remote e clona ELA — a base é
#      sempre uma release, nunca o main bleeding-edge. Fallback pra main só
#      se nenhuma tag de release existir.
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

# ── Clone (última release tag) ─────────────────────────────────────────────────
#
# feature-forge instala SEMPRE a partir da última release tag (v*), nunca do
# main bleeding-edge. Isto mantém a base de cada instalação numa release
# estável e versionada. Se nenhuma tag de release existir no remote, cai pra
# main como fallback (repo recém-criado, antes do primeiro release).
#
# --sort=-v:refname ordena semver descendente (git 2.18+); o filtro 'v*' pega
# apenas refs de release. Sed extrai o nome da tag do ref completo.

echo ""
echo "descobrindo a última release de feature-forge..."
LATEST_TAG=$(git ls-remote --tags --refs --sort=-v:refname "$FORGE_REPO_URL" 'v*' 2>/dev/null | head -n1 | sed 's#.*refs/tags/##')

echo ""
if [ -n "$LATEST_TAG" ]; then
  echo "🔨 instalando release $LATEST_TAG em $FORGE_HOME..."
  git clone --depth=1 --branch "$LATEST_TAG" "$FORGE_REPO_URL" "$FORGE_HOME"
else
  echo "🔨 nenhuma release tag encontrada — clonando main (fallback) em $FORGE_HOME..."
  git clone --depth=1 "$FORGE_REPO_URL" "$FORGE_HOME"
fi

# ── Venv + dependências ───────────────────────────────────────────────────────

echo ""
echo "criando ambiente virtual..."
python3 -m venv "$FORGE_HOME/.venv"

echo "instalando dependências..."
"$FORGE_HOME/.venv/bin/pip" install --quiet -e "$FORGE_HOME"

# ── Alias / binary conflict detection ────────────────────────────────────────
#
# Verifica se já existe um binário chamado 'forge' no PATH.
# Se sim, oferece 3-caminhos mentor-calmo:
#   A) Prosseguir — o symlink novo sobrescreve/ofusca o existente
#   B) Instalar como 'forge-cli' em vez de 'forge' (mantém ambos)
#   C) Abortar (exit 130)

BIN_NAME="forge"

if command -v forge >/dev/null 2>&1; then
  EXISTING_FORGE="$(command -v forge)"
  echo ""
  echo "🔨 forge: já existe binário 'forge' em $EXISTING_FORGE."
  echo ""
  echo "Três caminhos:"
  echo "  A) Prosseguir — instala feature-forge 'forge' (sobrescreve/ofusca o existente)"
  echo "  B) Instalar como 'forge-cli' em vez de 'forge' (mantém ambos disponíveis)"
  echo "  C) Abortar"
  echo ""

  _choice_conflict=""
  if [[ -t 0 ]]; then
    read -r -p "Escolha [A/B/C]: " _choice_conflict
  else
    read -r -p "Escolha [A/B/C]: " _choice_conflict </dev/tty
  fi

  _lc_conflict=$(printf '%s' "$_choice_conflict" | tr '[:upper:]' '[:lower:]')
  case "$_lc_conflict" in
    a)
      BIN_NAME="forge"
      echo "prosseguindo — 'forge' será instalado em ~/.local/bin/forge."
      ;;
    b)
      BIN_NAME="forge-cli"
      echo "instalando como 'forge-cli' — use 'forge-cli' para invocar feature-forge."
      ;;
    c)
      echo "abortado."
      exit 130
      ;;
    *)
      echo "escolha inválida — abortando."
      exit 4
      ;;
  esac
fi

# ── Symlink em ~/.local/bin ───────────────────────────────────────────────────

mkdir -p "$HOME/.local/bin"
ln -sf "$FORGE_HOME/bin/forge" "$HOME/.local/bin/${BIN_NAME}"

# ── PATH detection + 3-caminhos ──────────────────────────────────────────────
#
# Detecta se ~/.local/bin já está no PATH.
# Se não está, oferece 3-caminhos mentor-calmo:
#   A) Adicionar ao rc file automaticamente (marker-guarded para idempotência)
#   B) Mostrar a linha para o user adicionar manualmente
#   C) Pular (user é responsável por configurar PATH)
#
# Spec ref: §3 D.1 — PATH detection canonical

_forge_setup_path() {
  local rc_file=""
  local path_line=""
  local marker="# added by feature-forge install"

  # Detecta shell via $SHELL
  local user_shell
  user_shell="$(basename "${SHELL:-bash}")"

  case "$user_shell" in
    zsh)
      rc_file="$HOME/.zshrc"
      path_line='export PATH="$HOME/.local/bin:$PATH"'
      ;;
    bash)
      # Prefere .bash_profile em macOS (login shell), .bashrc em Linux
      if [[ -f "$HOME/.bash_profile" ]]; then
        rc_file="$HOME/.bash_profile"
      else
        rc_file="$HOME/.bashrc"
      fi
      path_line='export PATH="$HOME/.local/bin:$PATH"'
      ;;
    fish)
      rc_file="$HOME/.config/fish/config.fish"
      path_line='fish_add_path $HOME/.local/bin'
      ;;
    *)
      # Shell desconhecido — oferece linha genérica
      rc_file=""
      path_line='export PATH="$HOME/.local/bin:$PATH"'
      ;;
  esac

  echo ""
  echo "🔨 ~/.local/bin não está no PATH."
  echo ""
  echo "Três caminhos:"
  if [[ -n "$rc_file" ]]; then
    echo "  A) Adicionar automaticamente em $rc_file"
  else
    echo "  A) Imprimir linha para adicionar manualmente (shell $user_shell não reconhecido)"
  fi
  echo "  B) Mostrar a linha — você adiciona manualmente"
  echo "  C) Pular (configure PATH por conta própria depois)"
  echo ""

  local choice
  # Leitura interativa — funciona em terminal real; em pipe (curl | bash)
  # /dev/tty garante acesso ao terminal mesmo com stdin redirecionado.
  if [[ -t 0 ]]; then
    read -r -p "Escolha [A/B/C]: " choice
  else
    read -r -p "Escolha [A/B/C]: " choice </dev/tty
  fi

  _lc_choice=$(printf '%s' "$choice" | tr '[:upper:]' '[:lower:]')
  case "$_lc_choice" in
    a)
      if [[ -n "$rc_file" ]]; then
        # Idempotência: só adiciona se o marker ainda não existe
        if ! grep -qF "$marker" "$rc_file" 2>/dev/null; then
          {
            echo ""
            echo "$marker"
            echo "$path_line"
          } >> "$rc_file"
          echo "adicionado em $rc_file — reabra o terminal ou execute: source $rc_file"
        else
          echo "PATH já configurado em $rc_file (marker encontrado) — nenhuma alteração."
        fi
      else
        # Shell desconhecido: fallback pra imprimir
        echo ""
        echo "adicione ao seu rc file:"
        echo "  $path_line"
      fi
      ;;
    b)
      echo ""
      echo "adicione ao seu rc file:"
      echo "  $path_line"
      echo ""
      echo "depois execute: source <seu-rc-file>"
      ;;
    c)
      echo "PATH não configurado. Garanta que ~/.local/bin esteja no PATH antes de usar forge."
      ;;
    *)
      echo "escolha inválida — PATH não configurado. Adicione ~/.local/bin ao PATH manualmente."
      ;;
  esac
}

# Só executa PATH detection se ~/.local/bin ainda não está no PATH
if ! echo ":${PATH}:" | grep -q ":${HOME}/.local/bin:"; then
  _forge_setup_path
fi

# ── Smoke ─────────────────────────────────────────────────────────────────────

echo ""
if "$FORGE_HOME/bin/forge" --version >/dev/null 2>&1; then
  echo "✓ instalado. próximo: cd <projeto> && forge init"
else
  echo "aviso: instalação concluída mas smoke test falhou."
  echo "Tente: $FORGE_HOME/bin/forge --version"
fi
