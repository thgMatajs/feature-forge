"""Regression P-17: plan-complete must release the phase-lock sentinel.

Bug P-17 (pilot R5/R6, MeoBonsai): `forge implement` was blocked by a stale
phase-lock. The plan-complete block in ``engine.plan.run`` zeroed the
``status.json:phase-lock`` MIRROR but never removed the ``.phase-lock``
sentinel — the authoritative gate consulted first by ``current_phase_lock``.
The sources diverged: the mirror said ``None`` while the sentinel still held
``"planning"``. A subsequent ``forge implement`` hit ``FileExistsError``
(``"planning"`` != task_id) → ERR_LOCKED, and the error message printed
``by 'None'`` because it read the stale mirror.

Fix: plan-complete calls ``release_phase_lock`` (the canonical primitive that
removes the sentinel AND reconciles status.json) BEFORE persisting the final
``planned`` state — order matters because ``release_phase_lock`` overwrites
``last_action_kind`` to ``"phase-lock-released"``, so the ``planned`` /
``plan-completed`` write must come AFTER the release.
"""

from __future__ import annotations

from pathlib import Path

from engine import plan
from engine.memory.l1 import (
    acquire_phase_lock,
    current_phase_lock,
    read_l1_status,
    _phase_lock_path,
)


def _seed_planning_lock(project_root: Path, slug: str) -> None:
    """Seed an L1 in the exact post-acquire state ``forge plan`` plants.

    Creates the workflow-config marker, initializes status.json, then plants
    the ``"planning"`` sentinel + mirror via ``acquire_phase_lock`` — mirroring
    ``engine.plan.run`` L1908.
    """
    workflow_config = project_root / ".claude" / "workflow-config.yaml"
    if not workflow_config.exists():
        workflow_config.write_text("version: 1\n", encoding="utf-8")

    # Initialize the L1 status the same way plan.run does before acquire.
    plan._initialize_status(slug, project_root)
    assert acquire_phase_lock(slug, project_root, "planning") is True
    assert current_phase_lock(slug, project_root) == "planning"


def test_plan_complete_clears_sentinel_and_mirror(tmp_forge_project: Path):
    """After finalization the sentinel is gone and the mirror reads None."""
    slug = "rega-automatica"
    _seed_planning_lock(tmp_forge_project, slug)
    state = read_l1_status(slug, tmp_forge_project)
    assert state is not None

    plan._finalize_planned(slug, tmp_forge_project, state)

    # Sentinel-first read must report no lock.
    assert current_phase_lock(slug, tmp_forge_project) is None
    # The authoritative sentinel file is gone from disk.
    assert not _phase_lock_path(slug, tmp_forge_project).exists()
    # Mirror reconciled.
    final = read_l1_status(slug, tmp_forge_project)
    assert final is not None
    assert final.status == "planned"
    assert final.phase_lock is None


def test_plan_complete_invariant_order(tmp_forge_project: Path):
    """release_phase_lock must not leave last_action_kind=phase-lock-released.

    The finalization order (release FIRST, then persist planned) must win:
    the persisted state reads status=planned AND last_action_kind=plan-completed,
    not the phase-lock-released marker that release_phase_lock writes.
    """
    slug = "rega-automatica"
    _seed_planning_lock(tmp_forge_project, slug)
    state = read_l1_status(slug, tmp_forge_project)
    assert state is not None

    plan._finalize_planned(slug, tmp_forge_project, state)

    final = read_l1_status(slug, tmp_forge_project)
    assert final is not None
    assert final.status == "planned"
    assert final.last_action_kind == "plan-completed"
    assert final.phase_lock is None
