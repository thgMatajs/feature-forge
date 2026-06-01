"""Regression: phase lock must be released on every exception path (C2).

Bug C2 (PR #1): the critical section after ``acquire_phase_lock`` in
``engine.implement.run`` only handled ``PromptAbortedError`` for release —
any other exception (RuntimeError, OSError, KeyError, ...) bubbled out
with the lock still held, requiring the user to run ``forge undo`` to
recover.

Fix: a ``finally`` block (gated by a ``released`` flag so happy-path
explicit releases aren't double-called) guarantees the lock is cleared
on any exception path between acquisition and the function's return.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import implement
from engine.memory.l1 import current_phase_lock, read_l1_status


def _seed_ready_feature(project_root: Path, slug: str = "lembrete-rega") -> Path:
    """Create a feature directory passing the readiness gate with one task."""
    # workflow-config.yaml — find_project_root's marker.
    workflow_config = project_root / ".claude" / "workflow-config.yaml"
    if not workflow_config.exists():
        workflow_config.write_text("version: 1\n", encoding="utf-8")

    feature_root = (
        project_root
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    (feature_root / "tasks").mkdir(parents=True)

    # readiness — the handoff JSON path is the canonical signal
    (feature_root / "plan-feature-handoff.json").write_text(
        json.dumps({"readiness": {"status": "ready"}}),
        encoding="utf-8",
    )

    # one pending task with no external deps
    (feature_root / "tasks" / "TASK-001.yaml").write_text(
        "task_id: TASK-001\n"
        "description: smoke task\n"
        "allowed_files: []\n"
        "validations: []\n"
        "gates: []\n"
        "dependencies: []\n"
        "status: pending\n",
        encoding="utf-8",
    )

    # L1 status — implementing-ready (no phase_lock)
    memory_l1 = project_root / ".claude" / "memory" / "L1" / slug
    memory_l1.mkdir(parents=True, exist_ok=True)
    (memory_l1 / "status.json").write_text(
        json.dumps(
            {
                "feature-slug": slug,
                "status": "implementing",
                "last-action-at": "",
                "last-action-kind": "",
                "phase-lock": None,
                "subtype": "product",
            }
        ),
        encoding="utf-8",
    )
    return feature_root


def test_phase_lock_released_on_unexpected_exception(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A RuntimeError between acquire and release must NOT leak the lock."""
    slug = "lembrete-rega"
    _seed_ready_feature(tmp_forge_project, slug)
    monkeypatch.chdir(tmp_forge_project)

    # Confirm we start with no lock.
    assert current_phase_lock(slug, tmp_forge_project) is None

    # Force the critical section to blow up post-lock-acquire.
    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated mid-implement failure")

    monkeypatch.setattr(implement, "_print_plan_mode", boom)
    # confirm-prompt would block — force it autonomously.
    monkeypatch.setattr(
        "engine.ui.question.confirm", lambda *a, **kw: False, raising=False
    )
    monkeypatch.setattr(
        "engine.ui.question.ask", lambda *a, **kw: "abort", raising=False
    )

    with pytest.raises(RuntimeError, match="simulated"):
        implement.run([slug])

    # The critical assertion — without the try/finally fix, the lock stays
    # set to "TASK-001" forever and the user has to run `forge undo`.
    assert current_phase_lock(slug, tmp_forge_project) is None, (
        "Phase lock leaked — unhandled exception held the lock past return"
    )


def test_phase_lock_released_on_prompt_aborted(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Regression guard: the existing PromptAbortedError path still releases."""
    from engine.ui.question import PromptAbortedError

    slug = "lembrete-rega"
    _seed_ready_feature(tmp_forge_project, slug)
    monkeypatch.chdir(tmp_forge_project)

    def aborted(*_args, **_kwargs):
        raise PromptAbortedError("user ctrl-c")

    monkeypatch.setattr(implement, "_print_plan_mode", aborted)
    monkeypatch.setattr(
        "engine.ui.question.confirm", lambda *a, **kw: False, raising=False
    )
    monkeypatch.setattr(
        "engine.ui.question.ask", lambda *a, **kw: "abort", raising=False
    )

    rc = implement.run([slug])
    assert rc == 130
    assert current_phase_lock(slug, tmp_forge_project) is None


def test_phase_lock_released_on_happy_path(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Regression guard: happy-path release still happens (no double-release crash)."""
    slug = "lembrete-rega"
    _seed_ready_feature(tmp_forge_project, slug)
    monkeypatch.chdir(tmp_forge_project)

    # Plan Mode prints, user declines confirm → early return at line ~792.
    # _print_plan_mode is a no-op stub; confirm returns False so the function
    # exits cleanly before _apply_mode_handoff.
    monkeypatch.setattr(implement, "_print_plan_mode", lambda *a, **kw: None)
    monkeypatch.setattr(
        "engine.ui.question.confirm", lambda *a, **kw: False, raising=False
    )
    monkeypatch.setattr(
        "engine.ui.question.ask", lambda *a, **kw: "abort", raising=False
    )

    rc = implement.run([slug])
    assert rc == 0
    assert current_phase_lock(slug, tmp_forge_project) is None

    # Sanity: status.json still readable, no corruption.
    state = read_l1_status(slug, tmp_forge_project)
    assert state is not None
    assert state.phase_lock is None
