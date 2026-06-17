"""Pre-init exit code contract (Bug U1) + --help WARN suppression (Bug U2).

Bug U1 — unify exit codes:
  Running `forge graph`, `forge memory`, or `forge reconfigure` in a directory
  without `.claude/workflow-config.yaml` (no forge init yet) must exit 1 per
  SPEC §3 A.1. Before the fix these handlers returned 2 (intent-pause code),
  which violates the contract.

Bug U2 — suppress WARN in --help / -h / no-args path:
  `forge --help` (and -h, and bare `forge`) must never emit [WARN] cleanup
  noise on stderr. Before the fix the finally-cleanup in cli.main could
  emit a [WARN] line; for help/no-args the guard makes it unconditionally
  silent.

ENV scrub: tests that subprocess `bin/forge` must strip agentic env vars
(CLAUDECODE, OPENCODE_*, CODEX*, CURSOR_*) so `detect_host` resolves to the
non-agentic adapter regardless of the host running the suite.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

# Canonical repo root (bin/forge lives here).
REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_BIN = REPO_ROOT / "bin" / "forge"

_SCRUB_EXACT = ("CLAUDECODE", "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE")
_SCRUB_PREFIXES = ("OPENCODE_", "CODEX", "CURSOR_")


def _clean_env() -> dict[str, str]:
    """Scrubbed env with FORGE_HOME + PYTHONPATH wired to repo."""
    env = os.environ.copy()
    for key in list(env.keys()):
        if key in _SCRUB_EXACT or any(key.startswith(p) for p in _SCRUB_PREFIXES):
            env.pop(key)
    env["FORGE_HOME"] = str(REPO_ROOT)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


# ── Bug U1 — pre-init commands must exit 1 ────────────────────────────────────

_DIVERGENT_COMMANDS = ["graph", "memory", "reconfigure"]


@pytest.mark.parametrize("cmd", _DIVERGENT_COMMANDS)
def test_pre_init_returns_exit_1(tmp_path: Path, cmd: str) -> None:
    """Running forge <cmd> in a bare directory (no forge init) must exit 1.

    Before the fix: graph/memory/reconfigure returned 2 (intent-pause code),
    violating SPEC §3 A.1 which requires pre-init failures to exit 1.
    """
    r = subprocess.run(
        [str(FORGE_BIN), cmd],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    assert r.returncode == 1, (
        f"`forge {cmd}` pre-init returned {r.returncode}, expected 1.\n"
        f"stderr: {r.stderr!r}\n"
        f"stdout: {r.stdout!r}"
    )


def test_status_pre_init_still_exits_1(tmp_path: Path) -> None:
    """Regression guard: `forge status` must still exit 1 pre-init (reference cmd)."""
    r = subprocess.run(
        [str(FORGE_BIN), "status"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    assert r.returncode == 1, (
        f"`forge status` pre-init returned {r.returncode}, expected 1.\n"
        f"stderr: {r.stderr!r}"
    )


# ── Bug U2 — --help / -h / no-args must not emit [WARN] ──────────────────────


@pytest.mark.parametrize("args", [["--help"], ["-h"], []])
def test_help_emits_zero_warn(tmp_path: Path, args: list[str]) -> None:
    """forge --help / -h / (no args) must not emit [WARN] cleanup noise.

    The intent-log cleanup in cli.main's finally-block must be skipped or
    silenced for help/no-args paths so the output stays clean.
    """
    r = subprocess.run(
        [str(FORGE_BIN)] + args,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    assert "[WARN]" not in r.stderr, (
        f"`forge {' '.join(args) or '(no args)'}` emitted WARN on stderr.\n"
        f"stderr: {r.stderr!r}"
    )
    assert "failed to clear" not in r.stderr.lower(), (
        f"`forge {' '.join(args) or '(no args)'}` stderr contains 'failed to clear'.\n"
        f"stderr: {r.stderr!r}"
    )
