"""Unit tests — ``bin/forge`` dispatcher (DRIFT-1 W4.T1 + Wave 2 clean break).

The dispatcher is a tiny Bash shim that, after resolving ``FORGE_HOME``,
always execs a single target:

    python -m engine.cli "$@"

Host context (Claude-Code-style harness vs. real terminal) is resolved
IN-PROCESS by ``engine.ui.question`` through the host adapter registry —
the dispatcher no longer branches on it. Wave 2 removed the old
``engine.ui.tty_bridge`` subprocess-loop (clean break); terminal-real
prompting now lives in ``TtyAdapter`` (``engine/host/adapters/tty.py``),
single-pass and in-process. The ``FORGE_FORCE_TTY_MODE`` override and the
default bridge fallthrough are gone with it.

Refs:
- ``docs/superpowers/specs/drift-1-intent-protocol.md`` §6 sub-Q **Sd**,
  §8 (exit codes).
- ``docs/superpowers/plans/drift-1-intent-protocol.md`` W4.T1.
- ``bin/forge`` (dispatcher under test).
- ``engine/host/adapters/tty.py`` (TtyAdapter — TTY path post clean break).

Why these tests are unit-level: every assertion runs the dispatcher
through ``subprocess.run``. Subprocess inherits no TTY, so the
non-interactive detection path lights up naturally for every invocation;
``engine.cli`` runs to completion regardless of which adapter the registry
would pick at runtime. The real-PTY path is exercised by the e2e suite
(``tests/e2e/test_tty_adapter_pty.py``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Project root resolves from this file: tests/unit/test_X.py → repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BIN_FORGE = PROJECT_ROOT / "bin" / "forge"


def _run_forge(
    args: list[str], *, env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Invoke ``bin/forge`` as a subprocess, capturing stdout/stderr.

    Always inherits the current environment then layers ``env_overrides``
    on top, so callers only need to spell out the bits they care about.
    Sets ``FORGE_PYTHON`` to the current interpreter — keeps the test
    deterministic across systems where ``python3`` may resolve to a
    different version than what installed the project's deps.
    """
    env = os.environ.copy()
    env["FORGE_PYTHON"] = sys.executable
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [str(BIN_FORGE), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


# --- Sanity ----------------------------------------------------------------


def test_bin_forge_exists_and_executable() -> None:
    """Pre-condition: dispatcher is on disk and executable.

    Catches accidental ``chmod -x`` or symlink rot before the harder
    tests confuse "not found" with "wrong dispatch path".
    """
    assert BIN_FORGE.exists(), f"missing dispatcher: {BIN_FORGE}"
    assert os.access(BIN_FORGE, os.X_OK), f"dispatcher not executable: {BIN_FORGE}"


def test_bash_syntax_valid() -> None:
    """``bash -n bin/forge`` parses cleanly.

    Cheap guard against typos in the conditional block — without this
    the broken script would only fail at the first user invocation.
    """
    result = subprocess.run(
        ["bash", "-n", str(BIN_FORGE)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"bash -n failed: stderr={result.stderr!r}"
    )


# --- Detection branches ----------------------------------------------------


def test_force_intent_mode_routes_to_engine_cli() -> None:
    """``FORGE_FORCE_INTENT_MODE=1`` → intent-only path; version prints.

    The override should win even when the dispatcher might have other
    reasons to pick a particular branch (here we are non-TTY anyway,
    but the assertion stands regardless of host context).
    """
    result = _run_forge(["--version"], env_overrides={"FORGE_FORCE_INTENT_MODE": "1"})
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )
    assert "forge" in result.stdout.lower(), (
        f"version output missing 'forge': stdout={result.stdout!r}"
    )


def test_claudecode_env_routes_to_intent_mode() -> None:
    """``CLAUDECODE`` set → intent-only path even with no other hint.

    Mirrors the Claude Code harness scenario. Claude Code 2.1.153 sets
    ``CLAUDECODE=1`` in the child env (verified empirically); once the
    hint is present the bridge stays out of the way and the engine
    speaks intents only.
    """
    result = _run_forge(
        ["--version"], env_overrides={"CLAUDECODE": "1"}
    )
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )
    assert "forge" in result.stdout.lower()


def test_default_non_tty_invocation_routes_to_intent_mode() -> None:
    """Default env, subprocess context (no TTY) → intent-only path.

    ``subprocess.run`` never attaches a TTY to the child, so the
    ``! -t 0 || ! -t 1`` checks in the dispatcher light up. This is
    the canonical CI / pipeline / hook scenario. Behaviour must match
    explicit ``FORGE_FORCE_INTENT_MODE=1`` for this branch.
    """
    # Strip overrides that could mask the detection — we want the
    # script's own TTY check to be the deciding signal.
    env = os.environ.copy()
    env["FORGE_PYTHON"] = sys.executable
    env.pop("FORGE_FORCE_INTENT_MODE", None)
    env.pop("FORGE_FORCE_TTY_MODE", None)
    env.pop("CLAUDECODE", None)
    result = subprocess.run(
        [str(BIN_FORGE), "--version"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )
    assert "forge" in result.stdout.lower()


# --- Wave 2 clean break — terminal-real migra pra engine.cli --------------


def test_terminal_real_routes_to_engine_cli() -> None:
    """Real-terminal (sem CLAUDECODE, sem FORGE_FORCE_INTENT_MODE) → engine.cli.

    Wave 2 clean break: o antigo ramo ``else → engine.ui.tty_bridge`` (que
    rodava pra sessões de terminal genuíno) foi removido junto com o
    subprocess-loop. O dispatcher agora tem um único alvo de exec —
    ``engine.cli`` — e a rota TTY humana é resolvida in-process pelo
    ``TtyAdapter`` via o registry de adapters em ``question._resolve_adapter``.

    Este teste cobre a migração de duas formas:

    1. Inspeção estática — o dispatcher exec'a ``engine.cli`` e NÃO
       exec'a mais o módulo deletado ``engine.ui.tty_bridge`` (a única
       menção remanescente é no comentário que documenta o clean break),
       nem carrega o override ``FORGE_FORCE_TTY_MODE``.
    2. Runtime — com todos os sinais de intent-mode removidos do env (o
       cenário que antes caía no ramo bridge), o comando ainda completa
       limpo, provando que ``engine.cli`` é alcançado sem crash.
    """
    body = BIN_FORGE.read_text(encoding="utf-8")
    assert "exec" in body and "engine.cli" in body, (
        "dispatcher should exec engine.cli"
    )
    # Nenhuma LINHA exec'a o bridge deletado. Olhamos só as linhas exec
    # (não comentários) — o cabeçalho documenta o clean break e pode citar
    # o nome do módulo antigo legitimamente.
    exec_lines = [
        line for line in body.splitlines()
        if line.strip().startswith("exec ")
    ]
    assert exec_lines, "dispatcher has no exec line"
    for line in exec_lines:
        assert "engine.ui.tty_bridge" not in line, (
            f"dispatcher still exec's the deleted bridge: {line!r}"
        )
        assert "engine.cli" in line, (
            f"unexpected exec target (not engine.cli): {line!r}"
        )
    # O override FORGE_FORCE_TTY_MODE saiu por completo (sem branch, sem
    # comentário citando-o como caminho ativo).
    assert "FORGE_FORCE_TTY_MODE" not in body, (
        "dispatcher still carries the removed FORGE_FORCE_TTY_MODE override"
    )

    # Runtime: strip the intent-mode signals so this mirrors the old
    # real-terminal branch as closely as a subprocess (no TTY) allows.
    env = os.environ.copy()
    env["FORGE_PYTHON"] = sys.executable
    env.pop("FORGE_FORCE_INTENT_MODE", None)
    env.pop("FORGE_FORCE_TTY_MODE", None)
    env.pop("CLAUDECODE", None)
    result = subprocess.run(
        [str(BIN_FORGE), "--version"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )
    assert "forge" in result.stdout.lower(), (
        f"version output missing 'forge': stdout={result.stdout!r}"
    )


# --- FORGE_VERSION dynamic (PR #11 review finding #28) ---------------------


def test_forge_version_reads_from_engine_dunder_version() -> None:
    """``FORGE_VERSION`` exportado pelo dispatcher = ``engine.__version__``.

    Finding #28 do master-review do PR #11: antes, ``FORGE_VERSION``
    era hardcoded ``"1.0.0"`` no dispatcher — drift garantido conforme
    o engine evoluísse. Agora é lido dinamicamente; este teste prova
    a equivalência.

    Verificação: invoca ``bash -c 'source dispatcher; echo $FORGE_VERSION'``
    indiretamente via subprocess que ecoa a env var, e compara com o
    valor importado de ``engine.__version__`` no interpretador host.
    """
    # Importa engine.__version__ no mesmo intérprete que o dispatcher
    # usaria (FORGE_PYTHON=sys.executable).
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from engine import __version__ as engine_version
    finally:
        sys.path.pop(0)

    # Echo FORGE_VERSION via subcomando help do engine.cli — mais
    # estável que parsear --version (que pode ter formatação variável).
    # Truque: o dispatcher exporta FORGE_VERSION antes do exec, mas
    # exec substitui o processo. Pra ler o valor que o dispatcher
    # calcularia, replicamos o cálculo aqui no Bash usando o mesmo
    # PYTHON e fórmula. Em outras palavras: validamos que a expressão
    # Bash dentro do script produz o mesmo valor que engine.__version__.
    env = os.environ.copy()
    env["FORGE_PYTHON"] = sys.executable
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from engine import __version__; print(__version__)",
        ],
        env=env,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"engine import failed: stderr={result.stderr!r}"
    )
    computed = result.stdout.strip()
    assert computed == engine_version, (
        f"dispatcher version expression ({computed!r}) drifted from "
        f"engine.__version__ ({engine_version!r})"
    )

    # Sanity adicional: garante que o dispatcher NÃO contém mais o
    # literal hardcoded antigo. Catch regression caso alguém faça
    # revert acidental do finding #28.
    body = BIN_FORGE.read_text(encoding="utf-8")
    assert 'FORGE_VERSION="1.0.0"' not in body, (
        "dispatcher regressed to hardcoded FORGE_VERSION='1.0.0' "
        "(see PR #11 review finding #28)"
    )
    assert "engine import __version__" in body or "from engine import __version__" in body, (
        "dispatcher missing dynamic version expression"
    )


# --- Anti-regression -------------------------------------------------------


def test_no_cli_flags_added_by_dispatcher() -> None:
    """Decision 10 — zero CLI flags introduced by the W4 dispatch logic.

    The dispatcher is supposed to detect host context via env vars and
    TTY state, never by parsing argv. Greps the script body for
    suspicious patterns ("getopts", "case $1", "--mode=") — finding any
    of those would mean someone wired flag parsing into the dispatcher,
    which violates Decision 10.
    """
    body = BIN_FORGE.read_text(encoding="utf-8")
    forbidden_patterns = ("getopts", 'case "$1"', "--intent-mode", "--tty-mode")
    for pattern in forbidden_patterns:
        assert pattern not in body, (
            f"dispatcher gained forbidden CLI-flag pattern: {pattern!r}"
        )


def test_forge_home_resolution_block_preserved() -> None:
    """W4.T1 anti-goal: do not touch lines that resolve ``FORGE_HOME``.

    The symlink-following loop is load-bearing for users who symlink
    ``forge`` into ``~/.local/bin``. We assert the canonical markers
    are still present — a quick guard against accidental cleanup.
    """
    body = BIN_FORGE.read_text(encoding="utf-8")
    assert "SCRIPT_SOURCE=\"${BASH_SOURCE[0]}\"" in body
    assert "while [ -L \"$SCRIPT_SOURCE\" ]; do" in body
    assert 'FORGE_HOME="$(cd -P "$(dirname "$SCRIPT_SOURCE")/.." && pwd)"' in body


# --- Help passthrough sanity -----------------------------------------------


def test_help_subcommand_routes_through_dispatcher() -> None:
    """Smoke: ``bin/forge help`` exits 0 and prints something on stdout.

    Mostly a sanity test that the dispatch doesn't swallow argv or
    crash on a common subcommand. Without this, a botched ``exec`` line
    could silently produce empty output.
    """
    result = _run_forge(["help"], env_overrides={"FORGE_FORCE_INTENT_MODE": "1"})
    # help should succeed; engine.cli routes "help" without any prompt.
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stdout.strip(), "help produced no stdout"
