"""Test that `forge upgrade --help` is wired in cli.py dispatch.

TDD: test written before wiring. RED → FAIL (unknown subcommand).
GREEN → PASS after COMMANDS dict updated.

Spec §3 D.2. Plan Task 4.5.
ENV scrub: same pattern as test_exit_codes.py.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

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


def test_forge_upgrade_help_exit_zero() -> None:
    """forge upgrade --help must exit 0 and mention 'upgrade' in output."""
    r = subprocess.run(
        [str(FORGE_BIN), "upgrade", "--help"],
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    assert r.returncode == 0, (
        f"expected exit 0, got {r.returncode}\n"
        f"stdout: {r.stdout!r}\n"
        f"stderr: {r.stderr!r}"
    )
    combined = (r.stdout + r.stderr).lower()
    assert "upgrade" in combined, (
        f"expected 'upgrade' in output, got: {combined!r}"
    )
