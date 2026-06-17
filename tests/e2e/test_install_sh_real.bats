#!/usr/bin/env bats
# tests/e2e/test_install_sh_real.bats
#
# Roda o install.sh ÍNTEGRO (sem patches, sem extração de fragmentos) contra
# um GIT REMOTE FAKE LOCAL — file:// bare repo, zero rede. Cobre o caminho
# real que o test_install_sh.bats irmão omite deliberadamente:
#   descoberta de tag (git ls-remote) → validação semver → git clone --branch
#   → venv → pip install → symlink → smoke (forge --version).
#
# Por que isto complementa (e não substitui) test_install_sh.bats:
#   - O irmão testa funções isoladas com stubs e patches de portabilidade.
#   - Este testa o script inteiro num remote determinístico file://.
#
# Determinismo:
#   - Remote bare local populado com worktree mínimo instalável (pyproject
#     mínimo + bin/forge que responde --version). Tag semver real (v9.9.9).
#   - python3/pip stubados em $TMP/bin: venv vira mkdir + pip stub, install
#     vira no-op exit 0. Sem rede, sem build real, sem flakiness.
#   - HOME e XDG_DATA_HOME fakes em $TMP; ~/.local/bin pré-injetado no PATH
#     para que a detecção de PATH (que leria /dev/tty) seja pulada pelo guard.
#
# Concerns C1/C2 do irmão (bash 3.2 ${var,,} e read </dev/tty) NÃO são
# atacados aqui — fora do escopo deste teste de fidelidade. O caminho feliz
# coberto aqui não passa pelos blocos interativos (PATH já setado, sem
# binário 'forge' pré-existente no PATH controlado).
#
# Compatível com Bats 1.13+.

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/scripts/install.sh"

# ── setup/teardown ────────────────────────────────────────────────────────────

setup() {
    TMP="$(mktemp -d)"
    export TMP

    mkdir -p "$TMP/home" "$TMP/bin" "$TMP/data"
    export HOME="$TMP/home"
    # XDG_DATA_HOME controla FORGE_HOME → "$XDG_DATA_HOME/feature-forge".
    export XDG_DATA_HOME="$TMP/data"

    # ~/.local/bin pré-existente E no PATH: o install.sh pula a detecção de
    # PATH (que de outra forma leria /dev/tty e travaria sem terminal).
    mkdir -p "$HOME/.local/bin"

    # PATH CONTROLADO e mínimo: precisa de git + coreutils, mas NÃO pode
    # conter um binário 'forge' (o do próprio repo está no $PATH herdado e
    # dispararia o bloco interativo de conflito de alias, que lê /dev/tty e
    # trava sem terminal). Montamos a partir dos dirs de sistema + o dir do
    # git resolvido, garantindo zero 'forge' pré-existente.
    local git_dir
    git_dir="$(dirname "$(command -v git)")"
    export PATH="$TMP/bin:$HOME/.local/bin:$git_dir:/usr/bin:/bin:/usr/sbin:/sbin"

    # Stub pip de topo (o install.sh usa o pip DO venv, mas mantemos este
    # como rede de segurança caso algum caminho chame pip global).
    printf '#!/usr/bin/env bash\nexit 0\n' > "$TMP/bin/pip"
    chmod +x "$TMP/bin/pip"

    _write_python3_stub "3.13.0"
}

teardown() {
    rm -rf "$TMP"
}

# ── helper: stub python3 (versão OK + venv que cria pip stub) ─────────────────

_write_python3_stub() {
    local ver="${1:-3.13.0}"
    local major minor
    major="$(echo "$ver" | cut -d. -f1)"
    minor="$(echo "$ver" | cut -d. -f2)"

    cat > "$TMP/bin/python3" <<STUB
#!/bin/bash
case "\${1:-}" in
    --version) echo "Python $ver" ;;
    -c)
        [ "$major" -gt 3 ] && exit 0
        [ "$major" -eq 3 ] && [ "$minor" -ge 11 ] && exit 0
        exit 1
        ;;
    -m)
        # python3 -m venv <dir>: cria <dir>/bin/pip stub (install vira no-op).
        if [ "\${2:-}" = "venv" ]; then
            mkdir -p "\${3:-.venv}/bin"
            printf '#!/bin/bash\nexit 0\n' > "\${3:-.venv}/bin/pip"
            chmod +x "\${3:-.venv}/bin/pip"
        fi
        ;;
    *) exit 0 ;;
esac
STUB
    chmod +x "$TMP/bin/python3"
}

# ── helper: monta remote git fake local com tag semver ────────────────────────
#
# Cria:
#   $TMP/src        — worktree mínimo instalável (pyproject + bin/forge)
#   $TMP/remote.git — bare repo, recebe push de src com a tag $1
#
# $1 = nome da tag a criar (ex.: v9.9.9 ou garbage). $2 = branch default (main).
_make_fake_remote() {
    local tag="$1"
    local default_branch="${2:-main}"
    local src="$TMP/src"
    local remote="$TMP/remote.git"

    mkdir -p "$src/bin"

    # pyproject mínimo — não precisa instalar de verdade (pip é stub), mas
    # mantém o worktree realista para o clone.
    cat > "$src/pyproject.toml" <<'PYP'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "feature-forge-fake"
version = "9.9.9"
requires-python = ">=3.11"
PYP

    # bin/forge mínimo: responde --version com exit 0 (smoke real passa).
    cat > "$src/bin/forge" <<'FORGE'
#!/bin/bash
case "${1:-}" in
    --version) echo "feature-forge 9.9.9"; exit 0 ;;
    *) exit 0 ;;
esac
FORGE
    chmod +x "$src/bin/forge"

    git init --quiet --bare "$remote"

    (
        cd "$src"
        git init --quiet -b "$default_branch" .
        git config user.email "test@example.com"
        git config user.name "feature-forge test"
        git add -A
        git commit --quiet -m "fake forge release"
        git tag "$tag"
        git remote add origin "$remote"
        git push --quiet origin "$default_branch"
        git push --quiet origin "$tag"
    )
}

# ── testes ────────────────────────────────────────────────────────────────────

@test "install real: clona a tag semver válida, instala e smoke passa (exit 0)" {
    _make_fake_remote "v9.9.9"

    run env \
        FORGE_REPO_URL="file://$TMP/remote.git" \
        HOME="$HOME" \
        XDG_DATA_HOME="$XDG_DATA_HOME" \
        PATH="$PATH" \
        bash "$INSTALL_SH"

    [ "$status" -eq 0 ]
    # Caminho da release válida foi tomado.
    [[ "$output" == *"instalando release v9.9.9"* ]]
    # Smoke real passou.
    [[ "$output" == *"instalado"* ]]
    # FORGE_HOME foi clonado a partir da tag.
    [ -f "$XDG_DATA_HOME/feature-forge/bin/forge" ]
    [ -f "$XDG_DATA_HOME/feature-forge/pyproject.toml" ]
    # Symlink criado em ~/.local/bin.
    [ -L "$HOME/.local/bin/forge" ]
}

@test "install real: tag inválida no remote → fallback main + aviso (exit 0)" {
    # Remote SÓ tem uma tag 'garbage' (não-semver) — git ls-remote 'v*' não a
    # pega, e mesmo que pegasse a validação semver reprova. Para forçar o
    # caminho de detecção, criamos uma tag que casa o glob 'v*' do ls-remote
    # mas falha o semver estrito.
    _make_fake_remote "vGARBAGE"

    run env \
        FORGE_REPO_URL="file://$TMP/remote.git" \
        HOME="$HOME" \
        XDG_DATA_HOME="$XDG_DATA_HOME" \
        PATH="$PATH" \
        bash "$INSTALL_SH"

    [ "$status" -eq 0 ]
    # Caiu no fallback main com aviso mentor-calmo.
    [[ "$output" == *"fallback"* ]]
    [[ "$output" == *"clonando main"* ]]
    # NÃO tomou o caminho de release.
    [[ "$output" != *"instalando release"* ]]
    # Mesmo no fallback, a instalação completa e o smoke passa.
    [[ "$output" == *"instalado"* ]]
    [ -f "$XDG_DATA_HOME/feature-forge/bin/forge" ]
}
