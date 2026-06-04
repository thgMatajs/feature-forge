"""Tests for the cc-gate per-task hook integration in engine.implement.

Task 10 of the CC gate plan: `engine/implement.py` invokes the
``check_cyclomatic_complexity`` validator as an in-process Python call
between Review and Commit. The hook surfaces a 3-paths block on fail and
respects ``NO_CC_GATE=1`` as an audited emergency bypass.

Behavior contract:

- ``_run_cc_gate(project_root)`` returns a dict ``{"status": ..., ...,
  "blocking": bool}``. ``blocking`` is True iff the gate hard-failed.
- ``NO_CC_GATE=1`` env var → returns ``{"status": "warn", "blocking":
  False}`` AND appends one JSONL record to
  ``.claude/state/cc-gate-bypass.jsonl`` (path discoverable via
  ``_cc_bypass_log_path`` so tests can redirect it).
- When ``validate()`` returns ``status: "fail"``, ``_run_cc_gate``
  augments the result with ``blocking=True``.
- When ``validate()`` returns ``status: "pass"`` (e.g. CC-OVERRIDE in
  commit body silenced the offender inside the validator), the gate
  passes with ``blocking=False``.

These tests stub ``validators.check_cyclomatic_complexity.validate``
directly via ``sys.modules`` so they stay hermetic — no git / no tool
boots, only the engine-side glue is exercised.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

from engine import implement


def test_run_cc_gate_returns_pass_when_no_staged_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty repo / no staged files — gate is non-blocking (pass or warn)."""
    fake_pass = {"status": "pass", "message": "nenhum arquivo staged — nada a checar"}
    monkeypatch.setitem(
        sys.modules,
        "validators.check_cyclomatic_complexity",
        mock.MagicMock(validate=lambda root, **kw: fake_pass),
    )
    result = implement._run_cc_gate(tmp_path)
    assert result["status"] in {"pass", "warn"}
    assert result.get("blocking") is False


def test_run_cc_gate_blocks_on_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """validate() → status=fail makes the gate blocking and preserves 3-paths."""
    fake_fail = {
        "status": "fail",
        "message": "Cyclomatic Complexity gate: 1 função acima do limite",
        "paths": [
            {"kind": "fix", "label": "Refatorar", "motive": ""},
            {"kind": "revert", "label": "Override-justify no commit body", "motive": ""},
            {"kind": "split", "label": "Split-task", "motive": ""},
        ],
    }
    monkeypatch.setitem(
        sys.modules,
        "validators.check_cyclomatic_complexity",
        mock.MagicMock(validate=lambda root, **kw: fake_fail),
    )
    result = implement._run_cc_gate(tmp_path)
    assert result["status"] == "fail"
    assert result["blocking"] is True
    # The 3-paths block survives the wrapper unchanged.
    assert isinstance(result.get("paths"), list)
    assert len(result["paths"]) == 3


def test_run_cc_gate_bypassed_by_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """NO_CC_GATE=1 short-circuits to warn + appends an audit JSONL line."""
    monkeypatch.setenv("NO_CC_GATE", "1")
    bypass_log = tmp_path / ".claude" / "state" / "cc-gate-bypass.jsonl"
    monkeypatch.setattr(implement, "_cc_bypass_log_path", lambda root: bypass_log)

    # If validate is invoked, fail loud — bypass should skip the validator.
    def _must_not_call(*a: object, **kw: object) -> dict[str, object]:
        raise AssertionError("validator must not run when NO_CC_GATE=1")

    monkeypatch.setitem(
        sys.modules,
        "validators.check_cyclomatic_complexity",
        mock.MagicMock(validate=_must_not_call),
    )

    result = implement._run_cc_gate(tmp_path)
    assert result["status"] == "warn"
    assert result["blocking"] is False
    assert bypass_log.is_file(), "bypass log file must be created"
    contents = bypass_log.read_text(encoding="utf-8")
    assert "NO_CC_GATE" in contents
    # JSONL discipline — one record per bypass invocation.
    assert contents.strip().count("\n") == 0
    assert contents.endswith("\n")


def test_run_cc_gate_override_in_commit_body_permits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CC-OVERRIDE in commit body → validator returns pass → gate non-blocking."""
    fake_pass = {
        "status": "pass",
        "message": "cc-gate ok (1 silenced via override)",
    }
    monkeypatch.setitem(
        sys.modules,
        "validators.check_cyclomatic_complexity",
        mock.MagicMock(validate=lambda root, **kw: fake_pass),
    )
    result = implement._run_cc_gate(tmp_path)
    assert result["status"] == "pass"
    assert result["blocking"] is False
