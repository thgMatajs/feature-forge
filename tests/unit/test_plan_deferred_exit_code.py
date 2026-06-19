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
from engine.memory.l1 import read_l1_status
from engine.plan import WaveResult, _run_waves_for_subtype


def test_run_waves_for_subtype_returns_130_when_wave_defers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A deferred wave must return 130 AND persist deferred state (MD-02).

    MD-02 (review): the original test only verified the exit code. That
    leaves the contract under-pinned — the bug was "rc=0 silently marks a
    paused feature as planned", but a parallel regression is "rc=130
    without persisting deferred status". Real ``_run_static_wave`` calls
    ``_persist_deferred`` before returning a deferred WaveResult; the
    stub must mirror that or we lose visibility into the persist path.
    """
    slug = "paused-feature"

    def deferred_wave(label, templates, slug_arg, project_root, feature_path, **_kwargs):
        # Mirror the real wave's behavior: persist deferred BEFORE returning.
        plan_mod._persist_deferred(slug_arg, project_root, f"wave-{label.lower()}")
        return WaveResult(artefacts=[], deferred=True)

    # Stub Wave A — the first wave for any subtype — to defer.
    monkeypatch.setattr(plan_mod, "_run_static_wave", deferred_wave)

    rc = _run_waves_for_subtype(
        subtype="product",
        starting_wave="A",
        slug=slug,
        project_root=tmp_path,
        feature_path=tmp_path / "feature",
    )
    assert rc == 130, (
        "WaveResult.deferred=True must surface as exit code 130 (paused), "
        f"not 0 — got {rc}. The run() contract documents '0=ok, 130=paused'."
    )

    # MD-02: the deferred state must be persisted on disk too. Without
    # this assertion, a regression that returns 130 but skips
    # ``_persist_deferred`` would slip through — leaving the feature in
    # "planning" forever even though the user paused it.
    state = read_l1_status(slug, tmp_path)
    assert state is not None, (
        "status.json must exist after a deferred wave — _persist_deferred "
        "is responsible for writing it"
    )
    assert state.status == "deferred", (
        f"feature must be persisted as 'deferred', got {state.status!r}"
    )
    assert state.phase_lock is None, (
        "_persist_deferred must release the phase_lock — otherwise next "
        "`forge plan {slug}` is stuck on 'phase-locked by planning'"
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
