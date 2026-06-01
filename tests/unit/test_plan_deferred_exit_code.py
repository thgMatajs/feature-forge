"""Regression: deferred wave must propagate exit code 130 (A2).

Bug A2 (PR #1): ``engine.plan._run_waves_for_subtype`` returned ``0`` when
a wave handler reported ``WaveResult.deferred=True``. The caller (``run``)
then proceeded to "All waves consumed. Mark planned" — incorrectly marking
a paused feature as fully planned.

Per the run() docstring contract:
  '0=ok, 130=paused, other=hard gate'

Fix: ``_run_waves_for_subtype`` returns 130 on deferred. ``run`` already
short-circuits on non-zero rc, so the deferred state propagates correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import plan as plan_mod
from engine.plan import WaveResult, _run_waves_for_subtype


def test_run_waves_for_subtype_returns_130_when_wave_defers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A deferred wave must return 130, not 0."""

    def deferred_wave(*_args, **_kwargs) -> WaveResult:
        return WaveResult(artefacts=[], deferred=True)

    # Stub Wave A — the first wave for any subtype — to defer.
    monkeypatch.setattr(plan_mod, "_run_static_wave", deferred_wave)

    rc = _run_waves_for_subtype(
        subtype="product",
        starting_wave="A",
        slug="paused-feature",
        project_root=tmp_path,
        feature_path=tmp_path / "feature",
    )
    assert rc == 130, (
        "WaveResult.deferred=True must surface as exit code 130 (paused), "
        f"not 0 — got {rc}. The run() contract documents '0=ok, 130=paused'."
    )


def test_run_waves_for_subtype_returns_0_on_full_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """All waves finishing cleanly returns 0 (regression guard for happy path)."""

    def ok_wave(*_args, **_kwargs) -> WaveResult:
        return WaveResult(artefacts=[], deferred=False)

    monkeypatch.setattr(plan_mod, "_run_static_wave", ok_wave)
    monkeypatch.setattr(plan_mod, "_run_wave_d", ok_wave)
    monkeypatch.setattr(plan_mod, "_run_wave_e", ok_wave)

    rc = _run_waves_for_subtype(
        subtype="product",
        starting_wave="A",
        slug="happy-feature",
        project_root=tmp_path,
        feature_path=tmp_path / "feature",
    )
    assert rc == 0
