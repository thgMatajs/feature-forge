"""Unit tests — Gap 9 extends-feature mechanic.

Covers:
- L1State round-trip with extends_feature / parent_feature set + null
- read_l1_status forward-compat (pre-Gap-9 status.json without the fields)
- parent_state() happy path + parent missing
- list_extensions_of() happy + zero matches
- validate_extension_feature: no-op pass + happy extension + EXT-001..004 fails
- Canonical JSON shape on fail (status, what-failed, paths len == 3)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import validate_extension_feature as ve
from engine.memory import MemoryError
from engine.memory import l1


# ── Fixtures (local) ─────────────────────────────────────────────────────────


def _write_status(
    project_root: Path,
    slug: str,
    *,
    state: str = "done",
    extends: str | None = None,
    parent: str | None = None,
) -> None:
    """Helper — write a status.json directly without going through write_l1_status.

    Used to seed parent features and corruption scenarios. Caller controls
    every field — letting us simulate pre-Gap-9 files (no extends-feature key)
    or files with deliberately bad types.
    """
    d = project_root / ".claude" / "forge" / "state" / "lifecycle" / slug
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema-version": 1,
        "feature-slug": slug,
        "state": state,
        "subtype": "product",
        "last-action": "seeded",
        "last-action-at": "2026-06-03T10:00:00Z",
        "phase-lock": None,
    }
    if extends is not None or parent is not None:
        payload["extends-feature"] = extends
        payload["parent-feature"] = parent
    (d / "status.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_hypothesis(project_root: Path, slug: str, *, scope: str | None = None) -> None:
    """Helper — write hypothesis.yaml with optional extension-scope."""
    d = project_root / ".claude" / "forge" / "state" / "lifecycle" / slug
    d.mkdir(parents=True, exist_ok=True)
    data: dict = {"schema-version": 1, "feature-slug": slug}
    if scope is not None:
        data["extension-scope"] = scope
    (d / "hypothesis.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


# ── L1State round-trip ───────────────────────────────────────────────────────


def test_l1state_round_trip_with_extends_feature(tmp_forge_project: Path) -> None:
    """L1State carrying extends/parent persists + reads back identical."""
    state = l1.L1State(
        feature_slug="lembrete-rega-widget",
        status="planning",
        last_action_at="2026-06-03T10:00:00Z",
        last_action_kind="created",
        extends_feature="lembrete-rega",
        parent_feature="lembrete-rega",
    )
    l1.write_l1_status(state, tmp_forge_project)
    read = l1.read_l1_status("lembrete-rega-widget", tmp_forge_project)
    assert read is not None
    assert read.extends_feature == "lembrete-rega"
    assert read.parent_feature == "lembrete-rega"


def test_l1state_round_trip_with_null_extends(tmp_forge_project: Path) -> None:
    """Standalone feature (extends-feature null) round-trips as None."""
    state = l1.L1State(
        feature_slug="standalone",
        status="planning",
        last_action_at="2026-06-03T10:00:00Z",
        last_action_kind="created",
    )
    l1.write_l1_status(state, tmp_forge_project)
    read = l1.read_l1_status("standalone", tmp_forge_project)
    assert read is not None
    assert read.extends_feature is None
    assert read.parent_feature is None


def test_read_l1_status_forward_compat_no_fields(tmp_forge_project: Path) -> None:
    """Pre-Gap-9 status.json without extends/parent keys parses; defaults to None."""
    d = tmp_forge_project / ".claude" / "forge" / "state" / "lifecycle" / "legacy-feature"
    d.mkdir(parents=True)
    # No extends-feature / parent-feature in the payload — pre-Gap-9 shape.
    (d / "status.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "feature-slug": "legacy-feature",
                "state": "done",
                "subtype": "product",
                "last-action": "shipped",
                "last-action-at": "2026-05-01T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    read = l1.read_l1_status("legacy-feature", tmp_forge_project)
    assert read is not None
    assert read.extends_feature is None
    assert read.parent_feature is None


def test_read_l1_status_rejects_non_string_extends(tmp_forge_project: Path) -> None:
    """Type-safety: extends-feature as a dict / list is rejected (MemoryError)."""
    d = tmp_forge_project / ".claude" / "forge" / "state" / "lifecycle" / "corrupt"
    d.mkdir(parents=True)
    (d / "status.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "feature-slug": "corrupt",
                "state": "planning",
                "extends-feature": {"nested": "bad"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(MemoryError, match="extends-feature must be a slug string"):
        l1.read_l1_status("corrupt", tmp_forge_project)


# ── parent_state() helper ────────────────────────────────────────────────────


def test_parent_state_happy(tmp_forge_project: Path) -> None:
    """Extension feature points at done parent → parent_state returns 'done'."""
    _write_status(tmp_forge_project, "parent", state="done")
    _write_status(
        tmp_forge_project, "child", state="planning",
        extends="parent", parent="parent",
    )
    assert l1.parent_state("child", tmp_forge_project) == "done"


def test_parent_state_returns_none_for_standalone(tmp_forge_project: Path) -> None:
    """Feature with no extends-feature → parent_state returns None."""
    _write_status(tmp_forge_project, "solo", state="planning")
    assert l1.parent_state("solo", tmp_forge_project) is None


def test_parent_state_returns_none_when_parent_missing(tmp_forge_project: Path) -> None:
    """Extension pointing at non-existent parent → parent_state returns None."""
    _write_status(
        tmp_forge_project, "orphan", state="planning",
        extends="ghost", parent="ghost",
    )
    assert l1.parent_state("orphan", tmp_forge_project) is None


# ── list_extensions_of() helper ──────────────────────────────────────────────


def test_list_extensions_of_happy(tmp_forge_project: Path) -> None:
    """Two extensions of the same parent appear sorted; parent itself excluded."""
    _write_status(tmp_forge_project, "parent", state="done")
    _write_status(
        tmp_forge_project, "parent-widget", state="planning",
        extends="parent", parent="parent",
    )
    _write_status(
        tmp_forge_project, "parent-export", state="planning",
        extends="parent", parent="parent",
    )
    _write_status(tmp_forge_project, "unrelated", state="planning")
    extensions = l1.list_extensions_of("parent", tmp_forge_project)
    assert extensions == ["parent-export", "parent-widget"]


def test_list_extensions_of_zero_matches(tmp_forge_project: Path) -> None:
    """No L1 feature extends parent → empty list."""
    _write_status(tmp_forge_project, "parent", state="done")
    _write_status(tmp_forge_project, "solo", state="planning")
    assert l1.list_extensions_of("parent", tmp_forge_project) == []


def test_list_extensions_of_empty_input(tmp_forge_project: Path) -> None:
    """Empty parent_slug → empty list (defensive guard)."""
    _write_status(tmp_forge_project, "anything", state="planning")
    assert l1.list_extensions_of("", tmp_forge_project) == []


# ── validate_extension_feature ───────────────────────────────────────────────


def test_validator_pass_no_extensions(tmp_forge_project: Path) -> None:
    """No L1 feature declares extends-feature → no-op pass."""
    _write_status(tmp_forge_project, "feat-a", state="planning")
    _write_status(tmp_forge_project, "feat-b", state="done")
    result = ve.validate(tmp_forge_project)
    assert result["status"] == "pass"
    assert "nenhuma declara extends-feature" in result["message"]


def test_validator_pass_happy_extension(tmp_forge_project: Path) -> None:
    """Extension of a done parent with no peer scope collision → pass."""
    _write_status(tmp_forge_project, "lembrete", state="done")
    _write_status(
        tmp_forge_project, "lembrete-widget", state="planning",
        extends="lembrete", parent="lembrete",
    )
    _write_hypothesis(tmp_forge_project, "lembrete-widget", scope="android-widget")
    result = ve.validate(tmp_forge_project)
    assert result["status"] == "pass"
    assert "1 extension(s) válida(s)" in result["message"]


def test_validator_fail_ext_001_missing_parent(tmp_forge_project: Path) -> None:
    """EXT-001: parent slug não existe em L1 → fail com 3-paths."""
    _write_status(
        tmp_forge_project, "orphan-extension", state="planning",
        extends="ghost-parent", parent="ghost-parent",
    )
    result = ve.validate(tmp_forge_project)
    assert result["status"] == "fail"
    assert "EXT-001" in result["what-failed"]
    assert "ghost-parent" in result["what-failed"]
    assert len(result["paths"]) == 3
    # 3-paths canonical shape — fix / revert / split kinds.
    kinds = {p["kind"] for p in result["paths"]}
    assert kinds == {"fix", "revert", "split"}


def test_validator_fail_ext_002_parent_implementing(tmp_forge_project: Path) -> None:
    """EXT-002: parent em state=implementing (não done) → fail."""
    _write_status(tmp_forge_project, "still-cooking", state="implementing")
    _write_status(
        tmp_forge_project, "premature-extension", state="planning",
        extends="still-cooking", parent="still-cooking",
    )
    result = ve.validate(tmp_forge_project)
    assert result["status"] == "fail"
    assert "EXT-002" in result["what-failed"]
    assert "implementing" in result["what-failed"]
    assert len(result["paths"]) == 3


def test_validator_fail_ext_003_self_loop(tmp_forge_project: Path) -> None:
    """EXT-003: extends-feature == próprio slug → fail."""
    _write_status(
        tmp_forge_project, "navel-gazer", state="planning",
        extends="navel-gazer", parent="navel-gazer",
    )
    result = ve.validate(tmp_forge_project)
    assert result["status"] == "fail"
    assert "EXT-003" in result["what-failed"]
    assert "self-loop" in result["what-failed"]


def test_validator_fail_ext_004_duplicate_scope(tmp_forge_project: Path) -> None:
    """EXT-004: dois slugs estendem mesmo parent com mesmo scope → fail."""
    _write_status(tmp_forge_project, "parent", state="done")
    _write_status(
        tmp_forge_project, "ext-a", state="planning",
        extends="parent", parent="parent",
    )
    _write_status(
        tmp_forge_project, "ext-b", state="planning",
        extends="parent", parent="parent",
    )
    # Both declare identical extension-scope — colide.
    _write_hypothesis(tmp_forge_project, "ext-a", scope="android-widget")
    _write_hypothesis(tmp_forge_project, "ext-b", scope="android-widget")
    result = ve.validate(tmp_forge_project)
    assert result["status"] == "fail"
    assert "EXT-004" in result["what-failed"]
    assert "android-widget" in result["what-failed"]


def test_validator_fail_ext_004_empty_scope_collision(tmp_forge_project: Path) -> None:
    """EXT-004 (D-005): duas extensions do mesmo parent SEM hypothesis.yaml.

    Both default to empty-string scope and trip dedupe. Empty-scope-collision
    é o caso real-world mais comum — user esquece de declarar scope. Validator
    deve falhar com EXT-004 + label '(empty)' pra deixar claro que o
    remediation é declarar extension-scope explícito, não consolidar.
    """
    _write_status(tmp_forge_project, "parent", state="done")
    _write_status(
        tmp_forge_project, "ext-a", state="planning",
        extends="parent", parent="parent",
    )
    _write_status(
        tmp_forge_project, "ext-b", state="planning",
        extends="parent", parent="parent",
    )
    # NEITHER has hypothesis.yaml → both fallback to "" → collide.
    result = ve.validate(tmp_forge_project)
    assert result["status"] == "fail"
    assert "EXT-004" in result["what-failed"]
    # Mensagem cita '(empty)' como scope_repr — pista pro user declarar.
    assert "(empty)" in result["what-failed"]
    # 3-caminhos canônico continua presente no fail.
    assert "paths" in result
    assert len(result["paths"]) == 3


def test_validator_pass_distinct_scopes_same_parent(tmp_forge_project: Path) -> None:
    """Múltiplas extensions do mesmo parent com scopes distintos é OK."""
    _write_status(tmp_forge_project, "parent", state="done")
    _write_status(
        tmp_forge_project, "ext-android", state="planning",
        extends="parent", parent="parent",
    )
    _write_status(
        tmp_forge_project, "ext-ios", state="planning",
        extends="parent", parent="parent",
    )
    _write_hypothesis(tmp_forge_project, "ext-android", scope="android-widget")
    _write_hypothesis(tmp_forge_project, "ext-ios", scope="ios-watch")
    result = ve.validate(tmp_forge_project)
    assert result["status"] == "pass"


def test_validator_returns_structured_message(tmp_forge_project: Path) -> None:
    """Smoke: validator sempre retorna dict com 'status' e 'message' (string)."""
    result = ve.validate(tmp_forge_project)
    assert "status" in result
    assert isinstance(result.get("message", ""), str)


def test_validator_no_l1_dir_passes(tmp_project_root: Path) -> None:
    """Sem .claude/forge/state/lifecycle/ ainda — validator pass silencioso."""
    result = ve.validate(tmp_project_root)
    assert result["status"] == "pass"
    assert "L1 ausente" in result["message"]
