"""Regression P-17: lock-denied error message must show the REAL holder.

Bug P-17 (pilot R5/R6, MeoBonsai): when ``forge implement`` / ``forge plan``
were denied a phase-lock, the error message read the ``status.json`` MIRROR
(``read_l1_status(...).phase_lock``) to name the holder. Under the
sentinel-vs-mirror window the mirror can be stale ``None`` while a real lock is
held by the sentinel — so the message printed ``by 'None'``, masking the actual
holder and confusing the operator.

Fix: read the holder via ``current_phase_lock`` (sentinel-first) so the message
names the real owner of the lock.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import implement, plan
from engine.memory.l1 import current_phase_lock, read_l1_status, _phase_lock_path


def _plant_stale_sentinel(project_root: Path, slug: str, holder: str) -> None:
    """Write the sentinel directly, leaving the status.json mirror stale.

    Reproduces the genuine sentinel-vs-mirror window: the authoritative
    sentinel holds ``holder`` while ``status.json:phase_lock`` still reads
    ``None``. ``acquire_phase_lock`` can't reproduce this because it mirrors
    to status.json on success — so we bypass it and write the sentinel file
    on its own, exactly the state a mid-flight winner leaves behind.
    """
    lock_path = _phase_lock_path(slug, project_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(holder, encoding="utf-8")
    # Confirm the divergence we rely on: sentinel-first reads the holder,
    # mirror still reads None.
    assert current_phase_lock(slug, project_root) == holder
    mirror = read_l1_status(slug, project_root)
    assert mirror is not None and mirror.phase_lock is None


def _seed_ready_feature(project_root: Path, slug: str = "lembrete-rega") -> Path:
    """Create a feature dir passing the readiness gate with one pending task."""
    workflow_config = project_root / ".claude" / "workflow-config.yaml"
    if not workflow_config.exists():
        workflow_config.write_text("version: 1\n", encoding="utf-8")

    feature_root = (
        project_root
        / "docs"
        / "forge-specs"
        / "features"
        / slug
    )
    (feature_root / "tasks").mkdir(parents=True)
    (feature_root / "plan-feature-handoff.json").write_text(
        json.dumps({"readiness": {"status": "ready"}}),
        encoding="utf-8",
    )
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
    memory_l1 = project_root / ".claude" / "forge" / "state" / "lifecycle" / slug
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


def test_implement_lock_denied_shows_real_holder(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    """implement.run denied → message names the sentinel holder, not 'None'."""
    slug = "lembrete-rega"
    _seed_ready_feature(tmp_forge_project, slug)
    monkeypatch.chdir(tmp_forge_project)

    # Plant a FOREIGN lock so phase_lock_held can't acquire. The status.json
    # mirror still reads phase-lock=None (seeded above) — exactly the stale
    # window that produced "by 'None'".
    foreign = "OTHER-HOLDER-99"
    _plant_stale_sentinel(tmp_forge_project, slug, foreign)

    monkeypatch.setattr(
        "engine.ui.question.confirm", lambda *a, **kw: False, raising=False
    )
    monkeypatch.setattr(
        "engine.ui.question.ask", lambda *a, **kw: "abort", raising=False
    )

    rc = implement.run([slug])
    assert rc == 1
    captured = capsys.readouterr()
    assert f"phase-locked by '{foreign}'" in captured.err
    assert "by 'None'" not in captured.err
    assert "[FORGE-ERR:LOCKED]" in captured.err


def test_plan_lock_denied_shows_real_holder(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    """plan.run denied → message names the sentinel holder, not 'None'."""
    slug = "rega-automatica"
    workflow_config = tmp_forge_project / ".claude" / "workflow-config.yaml"
    workflow_config.write_text("version: 1\n", encoding="utf-8")

    # Seed an L1 in 'planned' (active, non-done) with a stale None mirror so
    # the collision path resolves to "retomar" (same slug), then the lock
    # acquire is denied by the foreign sentinel.
    memory_l1 = tmp_forge_project / ".claude" / "forge" / "state" / "lifecycle" / slug
    memory_l1.mkdir(parents=True, exist_ok=True)
    (memory_l1 / "status.json").write_text(
        json.dumps(
            {
                "feature-slug": slug,
                "status": "planned",
                "last-action-at": "",
                "last-action-kind": "",
                "phase-lock": None,
                "subtype": "product",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_forge_project)

    foreign = "OTHER-HOLDER-99"
    _plant_stale_sentinel(tmp_forge_project, slug, foreign)

    # Stub slug elicitation so run() proceeds with our seeded slug.
    monkeypatch.setattr(plan, "_elicit_slug", lambda *a, **kw: slug)
    monkeypatch.setattr(
        "engine.ui.question.confirm", lambda *a, **kw: False, raising=False
    )
    monkeypatch.setattr(
        "engine.ui.question.ask", lambda *a, **kw: "retomar", raising=False
    )

    rc = plan.run([slug])
    assert rc == 1
    captured = capsys.readouterr()
    assert f"phase-locked by '{foreign}'" in captured.err
    assert "by 'None'" not in captured.err
    assert "[FORGE-ERR:LOCKED]" in captured.err
