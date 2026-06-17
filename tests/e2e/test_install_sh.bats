#!/usr/bin/env bats
# tests/e2e/test_install_sh.bats
#
# Testa funções de install.sh SEM clonar o repo nem acessar a rede.
#
# Estratégia:
#   - HOME isolado em $TMP/home por cada test.
#   - Stubs de python3/pip em $TMP/bin sobrepõem os reais via PATH.
#   - Seções interativas são extraídas de install.sh, gravadas em scripts
#     temporários (evita quoting hell em bash -c), e executadas com stdin
#     piped para simular escolhas do usuário.
#   - Duas patches de portabilidade são aplicadas automaticamente:
#       a) remove "</dev/tty" — read piped já funciona sem tty
#       b) ${var,,} → $(echo "$var" | tr '[:upper:]' '[:lower:]')
#          (bash 3.2 macOS system default não suporta ${var,,})
#
# Cenários omitidos com comentário explícito:
#   - Clone real do github.com — git clone mockável de forma limitada;
#     prefere omitir a um stub instável que testa a cobertura errada.
#   - FORGE_HOME já existe guard — depende de sequência pós-clone.
#
# Concerns reportados (bugs em install.sh — NÃO corrigidos aqui):
#   C1) ${_choice_conflict,,} e ${choice,,} são bash 4+ e falham no
#       bash 3.2 que macOS expõe como /bin/bash (system default).
#       install.sh usa "#!/usr/bin/env bash" que resolve pra bash 3.2.
#   C2) read </dev/tty falha em subprocessos sem terminal alocado (CI,
#       subagent context). Cobre "curl | bash" em terminal real mas
#       não subprocessos comuns (subprocess.run, Agent dispatch).
#
# Compatível com Bats 1.13+.

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/scripts/install.sh"

# ── setup/teardown ────────────────────────────────────────────────────────────

setup() {
    TMP="$(mktemp -d)"
    export TMP

    mkdir -p "$TMP/home" "$TMP/bin" "$TMP/scripts"
    export HOME="$TMP/home"
    export PATH="$TMP/bin:$PATH"

    # Stub pip: sempre sucesso
    printf '#!/usr/bin/env bash\nexit 0\n' > "$TMP/bin/pip"
    chmod +x "$TMP/bin/pip"
}

teardown() {
    rm -rf "$TMP"
}

# ── helper: cria stub python3 com versão controlada ──────────────────────────

_write_python3_stub() {
    local ver="${1:-3.11.0}"
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
        mkdir -p "\${3:-.venv}/bin"
        printf '#!/bin/bash\nexit 0\n' > "\${3:-.venv}/bin/pip"
        chmod +x "\${3:-.venv}/bin/pip"
        ;;
    *) exit 0 ;;
esac
STUB
    chmod +x "$TMP/bin/python3"
}

# Extrai seção de install.sh e aplica patches de portabilidade.
# Grava em arquivo temporário ($1) para evitar quoting hell em bash -c.
# Patches:
#   - remove </dev/tty (read piped funciona sem tty)
#   - ${var,,} → tr tolower (compatibilidade bash 3.2)
_write_patched_section() {
    local outfile="$1"
    local section="$2"

    # Patch 1: remove </dev/tty
    section="$(echo "$section" | sed 's|</dev/tty||g')"
    # Patch 2: ${choice,,} → tr-based tolower
    section="$(echo "$section" | sed "s/\${choice,,}/\$(echo \"\$choice\" | tr '[:upper:]' '[:lower:]')/g")"
    # Patch 3: ${_choice_conflict,,} → tr-based tolower
    section="$(echo "$section" | sed "s/\${_choice_conflict,,}/\$(echo \"\$_choice_conflict\" | tr '[:upper:]' '[:lower:]')/g")"

    # Use /bin/bash explicitly so the shebang works even when PATH only has $TMP/bin
    printf '#!/bin/bash\n%s\n' "$section" > "$outfile"
    chmod +x "$outfile"
}

# ── testes ────────────────────────────────────────────────────────────────────

@test "python3 < 3.11 aborta com mensagem de erro" {
    _write_python3_stub "3.10.12"

    local ver_check full_path
    ver_check="$(sed -n '/^python3 -c.*sys.version/,/^}$/p' "$INSTALL_SH")"
    full_path="$TMP/bin:$PATH"
    _write_patched_section "$TMP/scripts/ver_check.sh" \
        "export PATH=\"$full_path\"
export HOME='$HOME'
$ver_check"

    run bash "$TMP/scripts/ver_check.sh"

    [ "$status" -ne 0 ]
    [[ "$output" == *"3.11"* ]] || [[ "$output" == *"necessário"* ]]
}

@test "python3 >= 3.11 passa verificação de pré-requisito" {
    _write_python3_stub "3.13.0"

    local ver_check full_path
    ver_check="$(sed -n '/^python3 -c.*sys.version/,/^}$/p' "$INSTALL_SH")"
    full_path="$TMP/bin:$PATH"
    _write_patched_section "$TMP/scripts/ver_check.sh" \
        "export PATH=\"$full_path\"
export HOME='$HOME'
$ver_check"

    run bash "$TMP/scripts/ver_check.sh"

    [ "$status" -eq 0 ]
}

@test "PATH detection zsh: adiciona linha no .zshrc quando ausente" {
    mkdir -p "$HOME"
    touch "$HOME/.zshrc"

    local func
    func="$(sed -n '/^_forge_setup_path()/,/^}$/p' "$INSTALL_SH")"
    _write_patched_section "$TMP/scripts/path_setup.sh" \
        "export HOME='$HOME'
$func
echo 'a' | SHELL=zsh _forge_setup_path"

    run bash "$TMP/scripts/path_setup.sh"

    [ "$status" -eq 0 ]
    [ -f "$HOME/.zshrc" ]
    grep -qF "added by feature-forge install" "$HOME/.zshrc"
}

@test "PATH detection zsh: idempotência — re-run não duplica entrada no .zshrc" {
    mkdir -p "$HOME"
    {
        printf '\n# added by feature-forge install\n'
        printf 'export PATH="$HOME/.local/bin:$PATH"\n'
    } > "$HOME/.zshrc"

    local before_count
    before_count="$(wc -l < "$HOME/.zshrc")"

    local func
    func="$(sed -n '/^_forge_setup_path()/,/^}$/p' "$INSTALL_SH")"
    _write_patched_section "$TMP/scripts/path_setup.sh" \
        "export HOME='$HOME'
$func
echo 'a' | SHELL=zsh _forge_setup_path"

    run bash "$TMP/scripts/path_setup.sh"

    [ "$status" -eq 0 ]

    local after_count
    after_count="$(wc -l < "$HOME/.zshrc")"

    # Linha count não cresceu (marker já existe — idempotente)
    [ "$after_count" -eq "$before_count" ]

    # Marker aparece exatamente 1 vez
    local marker_count
    marker_count="$(grep -c "added by feature-forge install" "$HOME/.zshrc")"
    [ "$marker_count" -eq 1 ]
}

@test "PATH já setado: pula edição do rc file" {
    mkdir -p "$HOME"
    touch "$HOME/.zshrc"
    local before_count
    before_count="$(wc -l < "$HOME/.zshrc")"

    local func
    func="$(sed -n '/^_forge_setup_path()/,/^}$/p' "$INSTALL_SH")"

    # Simula que ~/.local/bin já está no PATH → o bloco guard do install.sh
    # não deve invocar _forge_setup_path. Testamos o guard diretamente.
    _write_patched_section "$TMP/scripts/path_setup.sh" \
        "export HOME='$HOME'
$func
FAKE_PATH='$HOME/.local/bin:/usr/bin'
if ! echo \":\${FAKE_PATH}:\" | grep -q \":$HOME/.local/bin:\"; then
    echo 'a' | SHELL=zsh _forge_setup_path
fi
exit 0"

    run bash "$TMP/scripts/path_setup.sh"

    [ "$status" -eq 0 ]

    local after_count
    after_count="$(wc -l < "$HOME/.zshrc")"
    # .zshrc não foi modificado (guard impediu a chamada)
    [ "$after_count" -eq "$before_count" ]
}

@test "alias conflict: opção C aborta com exit 130" {
    # Cria stub 'forge' que simula binário existente no PATH
    mkdir -p "$TMP/forge_stub"
    printf '#!/bin/bash\necho "fake forge v0.1"\n' > "$TMP/forge_stub/forge"
    chmod +x "$TMP/forge_stub/forge"

    local alias_block full_path
    alias_block="$(sed -n '/^if command -v forge/,/^fi$/p' "$INSTALL_SH")"
    full_path="$TMP/forge_stub:$PATH"
    _write_patched_section "$TMP/scripts/alias_test.sh" \
        "export PATH=\"$full_path\"
export HOME='$HOME'
BIN_NAME=forge
$alias_block"

    run bash -c "echo 'c' | bash '$TMP/scripts/alias_test.sh'"

    [ "$status" -eq 130 ]
}

@test "smoke falho: instalação quebrada sai com exit != 0" {
    # Stub 'forge' que sempre falha em --version (instalação quebrada)
    mkdir -p "$TMP/forge_home/bin"
    printf '#!/bin/bash\nexit 3\n' > "$TMP/forge_home/bin/forge"
    chmod +x "$TMP/forge_home/bin/forge"

    local smoke_block
    smoke_block="$(sed -n '/^# ── Smoke/,$p' "$INSTALL_SH")"
    _write_patched_section "$TMP/scripts/smoke_test.sh" \
        "export HOME='$HOME'
FORGE_HOME='$TMP/forge_home'
$smoke_block"

    run bash "$TMP/scripts/smoke_test.sh"

    # Cross-AI review HIGH: smoke falho NÃO pode terminar com exit 0
    [ "$status" -ne 0 ]
    [[ "$output" == *"smoke test falhou"* ]]
}

@test "smoke OK: instalação saudável sai com exit 0" {
    # Stub 'forge' que responde --version com sucesso
    mkdir -p "$TMP/forge_home/bin"
    printf '#!/bin/bash\necho "forge 1.4.0"\nexit 0\n' > "$TMP/forge_home/bin/forge"
    chmod +x "$TMP/forge_home/bin/forge"

    local smoke_block
    smoke_block="$(sed -n '/^# ── Smoke/,$p' "$INSTALL_SH")"
    _write_patched_section "$TMP/scripts/smoke_test.sh" \
        "export HOME='$HOME'
FORGE_HOME='$TMP/forge_home'
$smoke_block"

    run bash "$TMP/scripts/smoke_test.sh"

    [ "$status" -eq 0 ]
    [[ "$output" == *"instalado"* ]]
}

@test "fish shell: _forge_setup_path usa fish_add_path" {
    mkdir -p "$HOME/.config/fish"
    touch "$HOME/.config/fish/config.fish"

    local func
    func="$(sed -n '/^_forge_setup_path()/,/^}$/p' "$INSTALL_SH")"
    _write_patched_section "$TMP/scripts/path_setup.sh" \
        "export HOME='$HOME'
$func
echo 'a' | SHELL=fish _forge_setup_path"

    run bash "$TMP/scripts/path_setup.sh"

    [ "$status" -eq 0 ]
    grep -qF "fish_add_path" "$HOME/.config/fish/config.fish"
}
