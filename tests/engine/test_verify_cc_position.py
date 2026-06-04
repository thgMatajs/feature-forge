"""Tests for the position of check_cyclomatic_complexity in the verify cascade.

Cobre Task 9 do CC gate plan: o validador `check_cyclomatic_complexity`
fica registrado como engine-default — imediatamente APÓS
`check_no_invented_behavior` — e a cascade respeita fail-fast (Decision 23):
quando o anterior falha hard, CC nem roda.
"""

from __future__ import annotations

from pathlib import Path

from engine import verify


def test_default_validators_registry_includes_cc_gate() -> None:
    assert hasattr(verify, "_DEFAULT_VALIDATORS")
    names = [entry["name"] for entry in verify._DEFAULT_VALIDATORS]
    assert "check_no_invented_behavior" in names
    assert "check_cyclomatic_complexity" in names


def test_cc_gate_positioned_after_no_invented_behavior() -> None:
    names = [entry["name"] for entry in verify._DEFAULT_VALIDATORS]
    idx_nib = names.index("check_no_invented_behavior")
    idx_cc = names.index("check_cyclomatic_complexity")
    assert idx_cc == idx_nib + 1, (
        f"CC gate must immediately follow check_no_invented_behavior; got {names}"
    )


def test_discover_validators_merges_default_registry(tmp_path: Path) -> None:
    """Mesmo sem cards ativos, os defaults do engine aparecem na cascade."""
    out = verify._discover_validators(tmp_path, {"cards": {"active": []}}, "feature")
    names = [spec.name for spec in out]
    assert "check_cyclomatic_complexity" in names
    assert "check_no_invented_behavior" in names


def test_cc_gate_skipped_when_no_invented_behavior_fails_failfast(
    monkeypatch, tmp_path: Path
) -> None:
    """Se check_no_invented_behavior falha hard, CC nem roda (fail-fast)."""
    captured: list[str] = []

    def fake_invoke(spec, root):
        captured.append(spec.name)
        if spec.name == "check_no_invented_behavior":
            return verify._ValidatorResult(
                name=spec.name, status="fail", duration_ms=1
            )
        return verify._ValidatorResult(
            name=spec.name, status="pass", duration_ms=1
        )

    monkeypatch.setattr(verify, "_invoke_validator", fake_invoke)
    specs = [
        verify._ValidatorSpec(
            name="check_no_invented_behavior", script_path=Path("nib.py")
        ),
        verify._ValidatorSpec(
            name="check_cyclomatic_complexity", script_path=Path("cc.py")
        ),
    ]
    results = verify._run_cascade(
        specs, fail_fast=True, project_root=tmp_path, interactive=False
    )
    cc_result = next(r for r in results if r.name == "check_cyclomatic_complexity")
    assert cc_result.status == "skipped"
    # CC nem foi invocado — fail-fast respeitado
    assert "check_cyclomatic_complexity" not in captured
