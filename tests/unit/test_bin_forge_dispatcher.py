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


def test_claude_code_host_env_routes_to_intent_mode() -> None:
    """``CLAUDE_CODE_HOST`` set → intent-only path even with no other hint.

    Mirrors the Claude Code harness scenario. Once the env hint is
    present the bridge stays out of the way and the engine speaks
    intents only.
    """
    result = _run_forge(
        ["--version"], env_overrides={"CLAUDE_CODE_HOST": "test-harness"}
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
    env.pop("CLAUDE_CODE_HOST", None)
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
