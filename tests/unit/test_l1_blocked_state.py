"""Unit tests for discipline §9 — External dependencies (Gap 8).

Covers:
- `blocked-on-external` state enum acceptance + invalid state still rejected
- L1State round-trip with state=blocked-on-external preserves value
- Forward compatibility: status.json without state=blocked still parses
- `blocking_deps()` reads task contracts and surfaces only unresolved
  blocking entries (filters: resolved-at filled, blocking=false)
- `is_blocked()` matches `blocking_deps() != []`
- `list_blocked_features()` walks the project
- `validate_task_contract.py` accepts depends_on_external when valid,
  fails it when malformed
- `engine.implement` refuses to start a blocked task (returns exit 7) and
  flips feature state to blocked-on-external on first refusal
- `engine.status` board renders the new "blocked on external" section
- `engine.reconfigure` external-deps handler resolves a ticket and flips
  state back to implementing

These tests must pass alongside the existing 318-test baseline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import validate_task_contract as v_task

from engine import implement, plan, status
from engine.memory import MemoryError, l1
from engine.memory.l1 import L1State


# ── state enum ──────────────────────────────────────────────────────────────


def test_blocked_on_external_is_accepted_state(tmp_path: Path) -> None:
    """L1State with state=blocked-on-external persists round-trip."""
    state = L1State(
        feature_slug="lembrete-rega",
        status="blocked-on-external",
        last_action_at="2026-05-30T10:00:00Z",
        last_action_kind="blocked-on-external-detected",
    )
    l1.write_l1_status(state, tmp_path)
    read = l1.read_l1_status("lembrete-rega", tmp_path)
    assert read is not None
    assert read.status == "blocked-on-external"


def test_invalid_state_still_rejected(tmp_path: Path) -> None:
    """Adding blocked-on-external should not silently widen the enum."""
    bad = L1State(
        feature_slug="x",
        status="not-a-real-state",
        last_action_at="2026-05-30T10:00:00Z",
        last_action_kind="x",
    )
    with pytest.raises(MemoryError):
        l1.write_l1_status(bad, tmp_path)


def test_legacy_status_without_blocked_state_still_parses(tmp_path: Path) -> None:
    """Forward-compat: status.json from pre-Gap-8 engines reads cleanly."""
    l1_dir = tmp_path / ".claude" / "memory" / "L1" / "legacy"
    l1_dir.mkdir(parents=True)
    legacy_payload = {
        "schema-version": 1,
        "feature-slug": "legacy",
        "state": "implementing",
        "last-action": "task-started",
        "last-action-at": "2026-04-01T10:00:00Z",
        "phase-lock": None,
    }
    (l1_dir / "status.json").write_text(
        json.dumps(legacy_payload), encoding="utf-8"
    )
    s = l1.read_l1_status("legacy", tmp_path)
    assert s is not None
    assert s.status == "implementing"
    assert s.subtype == "product"


# ── blocking_deps / is_blocked / list_blocked_features ──────────────────────


def _write_task_contract(
    project_root: Path,
    slug: str,
    task_id: str,
    ext_deps: list[dict[str, Any]],
) -> Path:
    """Helper: drop a minimal task YAML with the given depends_on_external."""
    tasks_dir = (
        project_root / "docs" / "feature-implementation-workflow"
        / "features" / slug / "tasks"
    )
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"{task_id}.yaml"
    import yaml

    payload = {
        "schema_version": 1,
        "task_id": task_id,
        "title": "stub",
        "feature_slug": slug,
        "layer": "data",
        "scope_in": [],
        "scope_out": [],
        "allowed_files": [],
        "bdd_scenarios_covered": [],
        "gates": [],
        "evidence_required": [
            "tests_passed",
            "files_touched",
            "validators_passed",
            "manual_verification_notes",
        ],
        "depends_on_external": ext_deps,
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    # Also seed a minimal status.json so subtype lookup works.
    l1.write_l1_status(
        L1State(
            feature_slug=slug,
            status="implementing",
            last_action_at="2026-05-30T10:00:00Z",
            last_action_kind="task-started",
        ),
        project_root,
    )
    return path


def test_blocking_deps_returns_empty_for_feature_without_tasks(
    tmp_forge_project: Path,
) -> None:
    """No tasks/ dir → empty list, no crash."""
    deps = l1.blocking_deps("nonexistent-feature", tmp_forge_project)
    assert deps == []


def test_blocking_deps_returns_empty_when_no_external_deps(
    tmp_forge_project: Path,
) -> None:
    """Task without depends_on_external → empty list."""
    _write_task_contract(tmp_forge_project, "lembrete-rega", "TASK-0001", [])
    deps = l1.blocking_deps("lembrete-rega", tmp_forge_project)
    assert deps == []


def test_blocking_deps_surfaces_blocking_unresolved_entry(
    tmp_forge_project: Path,
) -> None:
    """blocking=true + resolved-at=null → entry is returned."""
    _write_task_contract(
        tmp_forge_project,
        "lembrete-rega",
        "TASK-0003",
        [
            {
                "ticket": "BACKEND-1284",
                "integration": "jira",
                "description": "Endpoint /api/weather pendente",
                "blocking": True,
                "declared-at": "2026-05-30T10:00:00Z",
                "resolved-at": None,
            }
        ],
    )
    deps = l1.blocking_deps("lembrete-rega", tmp_forge_project)
    assert len(deps) == 1
    assert deps[0]["ticket"] == "BACKEND-1284"
    assert deps[0]["task"] == "TASK-0003"


def test_blocking_deps_filters_resolved_entries(
    tmp_forge_project: Path,
) -> None:
    """resolved-at filled → entry is hidden."""
    _write_task_contract(
        tmp_forge_project,
        "lembrete-rega",
        "TASK-0003",
        [
            {
                "ticket": "BACKEND-1284",
                "integration": "jira",
                "description": "ok",
                "blocking": True,
                "resolved-at": "2026-05-30T14:00:00Z",
            }
        ],
    )
    assert l1.blocking_deps("lembrete-rega", tmp_forge_project) == []


def test_blocking_deps_filters_non_blocking_entries(
    tmp_forge_project: Path,
) -> None:
    """blocking=false → informational, not surfaced."""
    _write_task_contract(
        tmp_forge_project,
        "lembrete-rega",
        "TASK-0003",
        [
            {
                "ticket": "DESIGN-44",
                "integration": "manual",
                "description": "banner copy",
                "blocking": False,
                "resolved-at": None,
            }
        ],
    )
    assert l1.blocking_deps("lembrete-rega", tmp_forge_project) == []


def test_is_blocked_mirrors_blocking_deps(tmp_forge_project: Path) -> None:
    """is_blocked is a thin Boolean wrapper."""
    assert l1.is_blocked("lembrete-rega", tmp_forge_project) is False
    _write_task_contract(
        tmp_forge_project,
        "lembrete-rega",
        "TASK-0003",
        [
            {
                "ticket": "BACKEND-1",
                "integration": "jira",
                "description": "x",
                "blocking": True,
                "resolved-at": None,
            }
        ],
    )
    assert l1.is_blocked("lembrete-rega", tmp_forge_project) is True


def test_list_blocked_features_returns_only_blocked(
    tmp_forge_project: Path,
) -> None:
    """Walks active L1, returns only slugs with unresolved blocking deps."""
    # Feature A: blocked.
    _write_task_contract(
        tmp_forge_project,
        "feature-a",
        "TASK-0001",
        [
            {
                "ticket": "BACKEND-99",
                "integration": "jira",
                "description": "x",
                "blocking": True,
                "resolved-at": None,
            }
        ],
    )
    # Feature B: clean.
    _write_task_contract(
        tmp_forge_project,
        "feature-b",
        "TASK-0001",
        [],
    )
    blocked = l1.list_blocked_features(tmp_forge_project)
    assert blocked == ["feature-a"]


# ── validator schema checks ─────────────────────────────────────────────────


def test_validator_accepts_well_formed_depends_on_external(
    tmp_forge_project_with_feature: Path,
) -> None:
    """Valid depends_on_external should not introduce violations."""
    tasks_dir = (
        tmp_forge_project_with_feature
        / "docs" / "feature-implementation-workflow"
        / "features" / "lembrete-rega" / "tasks"
    )
    (tasks_dir / "TASK-0001.yaml").write_text(
        "schema_version: 1\n"
        "task_id: TASK-0001\n"
        "title: stub\n"
        "feature_slug: lembrete-rega\n"
        "layer: data\n"
        "scope_in: []\n"
        "scope_out: []\n"
        "allowed_files: []\n"
        "bdd_scenarios_covered: []\n"
        "gates: []\n"
        "evidence_required:\n"
        "  - tests_passed\n"
        "  - files_touched\n"
        "  - validators_passed\n"
        "  - manual_verification_notes\n"
        "depends_on_external:\n"
        "  - ticket: BACKEND-1284\n"
        "    integration: jira\n"
        "    description: endpoint pendente\n"
        "    blocking: true\n"
        "    resolved-at: null\n",
        encoding="utf-8",
    )
    result = v_task.validate(
        tmp_forge_project_with_feature, scope="task", id="TASK-0001"
    )
    # We don't care about other unrelated violations; just that the
    # depends_on_external block didn't introduce one.
    if result["status"] == "fail":
        msg = (result.get("what-failed") or "").lower()
        assert "depends_on_external" not in msg


def test_validator_rejects_invalid_integration(
    tmp_forge_project_with_feature: Path,
) -> None:
    """integration must be in the allowed set."""
    tasks_dir = (
        tmp_forge_project_with_feature
        / "docs" / "feature-implementation-workflow"
        / "features" / "lembrete-rega" / "tasks"
    )
    (tasks_dir / "TASK-0001.yaml").write_text(
        "schema_version: 1\n"
        "task_id: TASK-0001\n"
        "title: stub\n"
        "feature_slug: lembrete-rega\n"
        "layer: data\n"
        "scope_in: []\n"
        "scope_out: []\n"
        "allowed_files: []\n"
        "bdd_scenarios_covered: []\n"
        "gates: []\n"
        "evidence_required:\n"
        "  - tests_passed\n"
        "  - files_touched\n"
        "  - validators_passed\n"
        "  - manual_verification_notes\n"
        "depends_on_external:\n"
        "  - ticket: BACKEND-1\n"
        "    integration: not-a-real-tracker\n"
        "    description: x\n"
        "    blocking: true\n",
        encoding="utf-8",
    )
    result = v_task.validate(
        tmp_forge_project_with_feature, scope="task", id="TASK-0001"
    )
    assert result["status"] == "fail"
    msg = (result.get("what-failed") or "")
    assert "integration" in msg


def test_validator_rejects_missing_ticket(
    tmp_forge_project_with_feature: Path,
) -> None:
    """ticket is a required key."""
    tasks_dir = (
        tmp_forge_project_with_feature
        / "docs" / "feature-implementation-workflow"
        / "features" / "lembrete-rega" / "tasks"
    )
    (tasks_dir / "TASK-0001.yaml").write_text(
        "schema_version: 1\n"
        "task_id: TASK-0001\n"
        "title: stub\n"
        "feature_slug: lembrete-rega\n"
        "layer: data\n"
        "scope_in: []\n"
        "scope_out: []\n"
        "allowed_files: []\n"
        "bdd_scenarios_covered: []\n"
        "gates: []\n"
        "evidence_required:\n"
        "  - tests_passed\n"
        "  - files_touched\n"
        "  - validators_passed\n"
        "  - manual_verification_notes\n"
        "depends_on_external:\n"
        "  - integration: jira\n"
        "    description: missing ticket\n",
        encoding="utf-8",
    )
    result = v_task.validate(
        tmp_forge_project_with_feature, scope="task", id="TASK-0001"
    )
    assert result["status"] == "fail"
    msg = (result.get("what-failed") or "")
    assert "ticket" in msg


# ── plan.record_external_dep ────────────────────────────────────────────────


def test_record_external_dep_persists_to_elicitation(
    tmp_forge_project: Path,
) -> None:
    """The helper writes to elicitation.yaml.external-deps[]."""
    entry = plan.record_external_dep(
        "lembrete-rega",
        tmp_forge_project,
        ticket="BACKEND-1284",
        integration="jira",
        description="endpoint pendente",
        task_hint="shared-data",
        blocking=True,
    )
    assert entry["ticket"] == "BACKEND-1284"
    elic = l1.read_elicitation("lembrete-rega", tmp_forge_project)
    assert elic is not None
    deps = elic.get("external-deps") or []
    assert len(deps) == 1
    assert deps[0]["task-hint"] == "shared-data"


def test_record_external_dep_dedupes_same_ticket_and_hint(
    tmp_forge_project: Path,
) -> None:
    """Re-recording the same (ticket, task-hint) replaces, doesn't duplicate."""
    plan.record_external_dep(
        "lembrete-rega",
        tmp_forge_project,
        ticket="BACKEND-1",
        integration="jira",
        description="first call",
        task_hint="shared-data",
    )
    plan.record_external_dep(
        "lembrete-rega",
        tmp_forge_project,
        ticket="BACKEND-1",
        integration="jira",
        description="second call (updated description)",
        task_hint="shared-data",
    )
    elic = l1.read_elicitation("lembrete-rega", tmp_forge_project)
    assert elic is not None
    deps = elic.get("external-deps") or []
    assert len(deps) == 1
    assert deps[0]["description"] == "second call (updated description)"


def test_record_external_dep_requires_ticket(tmp_forge_project: Path) -> None:
    """Empty ticket id is rejected — never invent."""
    with pytest.raises(ValueError):
        plan.record_external_dep(
            "x",
            tmp_forge_project,
            ticket="",
            integration="manual",
            description="vague",
            task_hint="shared-data",
        )


# ── engine.implement refusal path ───────────────────────────────────────────


def _seed_implementable_feature(
    project_root: Path,
    slug: str,
    *,
    blocked_tasks: list[str] | None = None,
) -> Path:
    """Set up a feature with readiness=ready + N tasks, optionally blocked.

    Returns the feature_path.
    """
    feature_root = (
        project_root / "docs" / "feature-implementation-workflow"
        / "features" / slug
    )
    feature_root.mkdir(parents=True, exist_ok=True)
    (feature_root / "tasks").mkdir(exist_ok=True)
    (feature_root / "plan-feature-handoff.json").write_text(
        json.dumps({"readiness_verdict": {"status": "ready"}}),
        encoding="utf-8",
    )
    # Always write at least one task — TASK-0001 — plus optional blocked tasks.
    _write_task_contract(project_root, slug, "TASK-0001", [])
    if blocked_tasks:
        for tid in blocked_tasks:
            _write_task_contract(
                project_root,
                slug,
                tid,
                [
                    {
                        "ticket": "BACKEND-1284",
                        "integration": "jira",
                        "description": "endpoint pendente",
                        "blocking": True,
                        "resolved-at": None,
                    }
                ],
            )
    return feature_root


def test_implement_refuses_blocked_task_and_flips_state(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run with only a blocked task → exit 7 + state=blocked-on-external."""
    # Single task, blocked.
    feature_root = (
        tmp_forge_project / "docs" / "feature-implementation-workflow"
        / "features" / "lembrete-rega"
    )
    feature_root.mkdir(parents=True, exist_ok=True)
    (feature_root / "tasks").mkdir(exist_ok=True)
    (feature_root / "plan-feature-handoff.json").write_text(
        json.dumps({"readiness_verdict": {"status": "ready-with-blocks"}}),
        encoding="utf-8",
    )
    _write_task_contract(
        tmp_forge_project,
        "lembrete-rega",
        "TASK-0001",
        [
            {
                "ticket": "BACKEND-1284",
                "integration": "jira",
                "description": "endpoint pendente",
                "blocking": True,
                "resolved-at": None,
            }
        ],
    )

    # Pretend we're inside the project (find_project_root walks up from cwd).
    # find_project_root walks up looking for workflow-config.yaml; seed one.
    (tmp_forge_project / ".claude" / "workflow-config.yaml").write_text(
        "identity: {project-name: stub, project-slug: stub, preset: kmp-mobile}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_forge_project)

    rc = implement.run(["lembrete-rega"])
    # C3 EXIT-2-COLLISION: return 7 (blocked-external) colapsou em exit 1 + tag.
    assert rc == 1

    s = l1.read_l1_status("lembrete-rega", tmp_forge_project)
    assert s is not None
    assert s.status == "blocked-on-external"


def test_implement_clears_blocked_when_deps_resolved(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When feature was blocked but the task now resolves, state flips back."""
    feature_root = (
        tmp_forge_project / "docs" / "feature-implementation-workflow"
        / "features" / "lembrete-rega"
    )
    feature_root.mkdir(parents=True, exist_ok=True)
    (feature_root / "tasks").mkdir(exist_ok=True)
    (feature_root / "plan-feature-handoff.json").write_text(
        json.dumps({"readiness_verdict": {"status": "ready"}}),
        encoding="utf-8",
    )
    # Task with resolved-at filled in — so it's no longer blocking.
    _write_task_contract(
        tmp_forge_project,
        "lembrete-rega",
        "TASK-0001",
        [
            {
                "ticket": "BACKEND-1284",
                "integration": "jira",
                "description": "endpoint pendente",
                "blocking": True,
                "resolved-at": "2026-05-30T14:00:00Z",
            }
        ],
    )
    # Seed status as blocked-on-external from a previous session.
    l1.write_l1_status(
        L1State(
            feature_slug="lembrete-rega",
            status="blocked-on-external",
            last_action_at="2026-05-30T10:00:00Z",
            last_action_kind="blocked-on-external-detected",
        ),
        tmp_forge_project,
    )

    # Seed workflow-config so find_project_root succeeds.
    if not (tmp_forge_project / ".claude" / "workflow-config.yaml").exists():
        (tmp_forge_project / ".claude" / "workflow-config.yaml").write_text(
            "identity: {project-name: stub, project-slug: stub, preset: kmp-mobile}\n",
            encoding="utf-8",
        )
    monkeypatch.chdir(tmp_forge_project)

    # We don't want to actually run the Plan Mode confirmation; intercept
    # question.confirm to refuse the plan (which exits without applying).
    from engine.ui import question as ui_q

    monkeypatch.setattr(ui_q, "confirm", lambda *_a, **_kw: False)

    implement.run(["lembrete-rega"])

    s = l1.read_l1_status("lembrete-rega", tmp_forge_project)
    assert s is not None
    # State was flipped back to implementing at startup once we saw the
    # deps were resolved.
    assert s.status in {"implementing"}


# ── engine.status board rendering ───────────────────────────────────────────


def test_status_renders_blocked_section(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Board renders a dedicated `blocked on external` section."""
    # Minimal workflow-config so status.run() doesn't bail.
    cfg_path = tmp_forge_project / ".claude" / "workflow-config.yaml"
    cfg_path.write_text(
        "identity:\n"
        "  project-name: stub\n"
        "  project-slug: stub\n"
        "  preset: kmp-mobile\n",
        encoding="utf-8",
    )

    # Seed one blocked feature.
    _write_task_contract(
        tmp_forge_project,
        "lembrete-rega",
        "TASK-0001",
        [
            {
                "ticket": "BACKEND-1284",
                "integration": "jira",
                "description": "endpoint pendente",
                "blocking": True,
                "resolved-at": None,
            }
        ],
    )
    l1.write_l1_status(
        L1State(
            feature_slug="lembrete-rega",
            status="blocked-on-external",
            last_action_at="2026-05-30T10:00:00Z",
            last_action_kind="blocked-on-external-detected",
        ),
        tmp_forge_project,
    )

    monkeypatch.chdir(tmp_forge_project)
    rc = status.run([])
    captured = capsys.readouterr().out
    assert rc == 0
    assert "blocked on external" in captured
    assert "BACKEND-1284" in captured
