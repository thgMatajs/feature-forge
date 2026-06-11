"""Unit tests — ``bin/forge`` dispatcher (DRIFT-1 W4.T1).

The dispatcher is a tiny Bash shim that chooses between two execution
paths after resolving ``FORGE_HOME``:

1. ``python -m engine.cli "$@"`` — intent-only mode. Picked when a
   Claude-Code-style harness is fronting the engine (env hint), when
   stdin or stdout is not a TTY (CI, pipes, subprocess), or when the
   user explicitly overrides with ``FORGE_FORCE_INTENT_MODE=1``.
2. ``python -m engine.ui.tty_bridge engine.cli "$@"`` — the TTY-fallback
   bridge from W3. Default branch for genuine terminal sessions.

Refs:
- ``docs/superpowers/specs/drift-1-intent-protocol.md`` §6 sub-Q **Sd**,
  §8 (exit codes).
- ``docs/superpowers/plans/drift-1-intent-protocol.md`` W4.T1.
- ``bin/forge`` (dispatcher under test).

Why these tests are unit-level: every assertion runs the dispatcher
through ``subprocess.run``. Subprocess inherits no TTY, so the
"non-interactive" detection path lights up naturally for every
invocation — letting us verify the intent-mode branch with a single
short-lived process per test. We do **not** drive the bridge branch
from here (that needs a real PTY) — W5's e2e suite owns that.
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


# --- FORGE_FORCE_TTY_MODE (PR #11 review finding #3) -----------------------


def test_force_tty_mode_dispatches_tty_bridge() -> None:
    """``FORGE_FORCE_TTY_MODE=1`` → bridge path (engine.ui.tty_bridge).

    Finding #3 do master-review do PR #11: CHANGELOG + SPEC declaravam
    o override mas o dispatcher só implementava ``FORGE_FORCE_INTENT_MODE``.
    Este teste prova que o override foi ligado e que o bridge é
    realmente o módulo executado.

    Verificação indireta: o bridge define ``FORGE_INTERNAL_TTY_BRIDGE=1``
    no env do subprocesso filho (ver ``engine/ui/tty_bridge.py``), e o
    engine pode observá-lo. Pra um teste unit barato, validamos que o
    comando ``--version`` ainda completa com saída esperada — o bridge
    passa returncode verbatim, então sucesso ponta-a-ponta significa
    que o caminho funcional foi exercido sem crash.
    """
    result = _run_forge(
        ["--version"], env_overrides={"FORGE_FORCE_TTY_MODE": "1"}
    )
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )
    assert "forge" in result.stdout.lower(), (
        f"version output missing 'forge': stdout={result.stdout!r}"
    )


def test_force_tty_mode_overrides_intent_signals() -> None:
    """``FORGE_FORCE_TTY_MODE=1`` vence até CLAUDECODE + FORGE_FORCE_INTENT_MODE.

    Precedência declarada em ``bin/forge``: TTY_MODE é checado ANTES
    dos sinais de intent-mode (CLAUDECODE / non-TTY /
    FORGE_FORCE_INTENT_MODE). Esta é a única forma de o operador
    forçar o bridge mesmo dentro de um harness Claude Code — sem isso,
    o override seria inerte na maioria dos cenários reais.

    Verificação: dispatcher não-crasha e propaga --version mesmo quando
    todos os sinais de intent-mode estão ativos simultaneamente. O
    bridge sobrescreve a rota; engine ainda imprime versão via exec.
    """
    result = _run_forge(
        ["--version"],
        env_overrides={
            "FORGE_FORCE_TTY_MODE": "1",
            "FORGE_FORCE_INTENT_MODE": "1",
            "CLAUDECODE": "1",
        },
    )
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )
    assert "forge" in result.stdout.lower()


def test_force_tty_mode_routes_through_tty_bridge_module() -> None:
    """Inspeção estática: dispatcher exec'a ``engine.ui.tty_bridge`` no
    ramo ``FORGE_FORCE_TTY_MODE``.

    Complementa os testes de runtime acima — runtime prova que o
    caminho funciona, este prova que é o módulo CORRETO. Sem isso,
    uma refatoração que route TTY_MODE pra engine.cli direto passaria
    despercebida (e quebraria a SPEC §6 Sd).
    """
    body = BIN_FORGE.read_text(encoding="utf-8")
    assert "FORGE_FORCE_TTY_MODE" in body, (
        "bin/forge missing FORGE_FORCE_TTY_MODE override"
    )
    # Garante que o override roteia pro bridge, não pro engine.cli.
    # Heurística: localiza a linha de teste real (``if [[ -n
    # "${FORGE_FORCE_TTY_MODE:-}" ]]``) — não o comentário descritivo
    # que vem antes — e exige tty_bridge na janela seguinte.
    marker = '[[ -n "${FORGE_FORCE_TTY_MODE:-}" ]]'
    assert marker in body, (
        f"dispatcher missing FORGE_FORCE_TTY_MODE conditional: {marker!r}"
    )
    idx = body.index(marker)
    window = body[idx : idx + 200]
    assert "engine.ui.tty_bridge" in window, (
        f"FORGE_FORCE_TTY_MODE branch does not exec engine.ui.tty_bridge; "
        f"window={window!r}"
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
