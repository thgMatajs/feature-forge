"""Unit tests for discipline §8 — Non-product feature track.

Covers:
- subtype keyword detection from free-form input (`detect_subtype_from_input`)
- wave-order branching per subtype (`_wave_order_for_subtype`)
- status.json forward compatibility (missing `subtype` → "product")
- L1State `subtype` round-trip + validation
- `check_no_behavior_change` validator behaviour on:
    · clean diff under subtype=refactor → pass
    · diff touching test files under subtype=refactor → fail with 3-caminhos
    · subtype=product → pass (gate inactive)

These tests must pass alongside the existing 287-test baseline. The plan
module's `run()` entry is exercised through dedicated smoke tests; this
file focuses on the deterministic helpers + the new validator.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import plan
from engine.memory import MemoryError
from engine.memory import l1
from engine.memory.l1 import L1State


# ── subtype keyword detection ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        # refactor signals
        ("mover MeoButton de organisms pra atoms, sem mudança visual", "refactor"),
        ("refactor: rename feature/bonsai/ui/list/ to feature/bonsai/list/", "refactor"),
        ("extrair helper compartilhado entre features de bonsai", "refactor"),
        ("Migrar Nav2 → Nav3 em feature/auth, comportamento inalterado", "refactor"),
        # bugfix signals (Gap 1)
        ("bugfix: validação de nome vazio aceita só espaços", "bugfix"),
        ("hotfix urgente — app crasha quando user clica em salvar", "bugfix"),
        ("P0 em produção: usuários não conseguem fazer login", "bugfix"),
        ("fix do bug de push notification dobrada em iOS 17.4+", "bugfix"),
        ("regression no fluxo de checkout depois do release", "bugfix"),
        ("Plano para corrigir falha do submit do formulário", "bugfix"),
        # spike signals
        ("Spike: avaliar viabilidade de Compose Multiplatform pra Web", "spike"),
        ("POC do novo módulo de notificações", "spike"),
        ("Investigar se conseguimos usar SKIE 0.10 em iOS", "spike"),
        # chore signals
        ("Bump kotlin 2.0 → 2.1 + cleanup do build.gradle", "chore"),
        ("Atualizar dependência do Ktor pra 3.0", "chore"),
        ("Chore: limpar warnings de detekt no shared", "chore"),
        # product (default)
        ("Criar tela de lembrete de rega por bonsai", "product"),
        ("Adicionar push notification quando lembrete dispara", "product"),
        ("", "product"),
    ],
)
def test_detect_subtype_from_input(text: str, expected: str) -> None:
    """Free-form input → inferred subtype via keyword matching."""
    assert plan.detect_subtype_from_input(text) == expected


# ── Bugfix ticket-pattern detection (Gap 1) ──────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        # High-confidence bugfix prefixes — bumped to bugfix even without
        # explicit keywords.
        ("Investigar IN-37234 que apareceu no crashlytics", "bugfix"),
        ("PD-1234 reportado pelo PM", "bugfix"),
        ("BUG-0001 está bloqueando o release", "bugfix"),
        # Generic feature tickets — NOT bumped (must remain product).
        ("BONSAI-1284: criar tela de lembrete de rega", "product"),
        ("LIN-456: nova feature de export", "product"),
        # Backend ticket — ambiguous, NOT in whitelist → product.
        ("BACKEND-1284 vai entregar novo endpoint", "product"),
    ],
)
def test_detect_subtype_ticket_pattern_bumps_bugfix(text: str, expected: str) -> None:
    """Ticket patterns IN-/PD-/BUG- bump to bugfix; generic tickets don't."""
    assert plan.detect_subtype_from_input(text) == expected


def test_detect_subtype_keyword_beats_generic_ticket() -> None:
    """Explicit bugfix keyword wins even with a non-whitelist ticket."""
    text = "BACKEND-1284 cobre o hotfix do crash de login"
    # "hotfix" + "crash" keywords already trigger bugfix; ticket is moot.
    assert plan.detect_subtype_from_input(text) == "bugfix"


def test_detect_subtype_priority_refactor_over_spike() -> None:
    """When both refactor and spike keywords appear, refactor wins (longer signal).

    Reflects the discipline-§8 precedence: when in doubt, prefer the more
    structured subtype. Conductor surfaces ambiguity via Cena 2.5 anyway.
    """
    text = "spike refactor do módulo de auth"
    assert plan.detect_subtype_from_input(text) == "refactor"


def test_detect_subtype_priority_refactor_over_bugfix() -> None:
    """When both refactor and bugfix keywords appear, refactor wins.

    Conductor will surface the ambiguity in Cena 2.5 — but the engine's
    inference defaults to the more structured subtype. Bugfix is the
    short-form fix; refactor is the explicit architectural restructure
    (more deliberate).
    """
    text = "refactor pra corrigir o bug de validação"
    assert plan.detect_subtype_from_input(text) == "refactor"


def test_detect_subtype_priority_bugfix_over_spike() -> None:
    """Bugfix wins over spike when both signals appear.

    Bugfix is concrete (known bug + fix path); spike is exploration.
    When the input mentions both, the concrete signal wins.
    """
    text = "spike pra investigar o bug do push notification"
    assert plan.detect_subtype_from_input(text) == "bugfix"


def test_detect_subtype_priority_product_when_only_ticket() -> None:
    """A pure feature description with no bugfix keyword stays product even with a generic ticket."""
    text = "Adicionar tela de configurações de notificação (BONSAI-4242)"
    assert plan.detect_subtype_from_input(text) == "product"


def test_detect_subtype_returns_product_for_non_string() -> None:
    """Defensive: invalid input types fall back to product without crashing."""
    assert plan.detect_subtype_from_input(None) == "product"  # type: ignore[arg-type]
    assert plan.detect_subtype_from_input(123) == "product"  # type: ignore[arg-type]


# ── wave-order branching ─────────────────────────────────────────────────────


def test_wave_order_product_full_sequence() -> None:
    """subtype=product → all 5 waves run in order."""
    assert plan._wave_order_for_subtype("product") == ("A", "B", "C", "D", "E")


def test_wave_order_refactor_skips_wave_b() -> None:
    """subtype=refactor → Wave B explicitly skipped."""
    order = plan._wave_order_for_subtype("refactor")
    assert "B" not in order
    assert order == ("A", "C", "D", "E")


def test_wave_order_bugfix_logic_only_skips_wave_b() -> None:
    """subtype=bugfix with wave_b_required=False → Wave B skipped (logic-only)."""
    order = plan._wave_order_for_subtype("bugfix", wave_b_required=False)
    assert "B" not in order
    assert order == ("A", "C", "D", "E")


def test_wave_order_bugfix_ui_observable_runs_wave_b() -> None:
    """subtype=bugfix with wave_b_required=True → Wave B runs (UI/observable)."""
    order = plan._wave_order_for_subtype("bugfix", wave_b_required=True)
    assert order == ("A", "B", "C", "D", "E")


def test_wave_order_bugfix_none_defaults_to_skipping_wave_b() -> None:
    """subtype=bugfix with wave_b_required=None defaults to logic-only.

    Defensive default — conductor SHOULD always supply the flag from
    hypothesis.yaml. None means "not elicited yet" and we choose the
    cheaper-on-failure path (skip Wave B).
    """
    order = plan._wave_order_for_subtype("bugfix", wave_b_required=None)
    assert order == ("A", "C", "D", "E")


def test_wave_order_unknown_subtype_falls_back_to_product() -> None:
    """Defensive: unknown subtype gets the safe product sequence.

    Spike/chore should never reach this function (caller short-circuits via
    the stub handler); if they do, treating as product is conservative.
    """
    assert plan._wave_order_for_subtype("spike") == ("A", "B", "C", "D", "E")
    assert plan._wave_order_for_subtype("chore") == ("A", "B", "C", "D", "E")
    assert plan._wave_order_for_subtype("bogus") == ("A", "B", "C", "D", "E")


# ── L1State subtype round-trip ───────────────────────────────────────────────


def test_l1state_default_subtype_is_product() -> None:
    """L1State has subtype=product by default (backward compatibility)."""
    state = L1State(
        feature_slug="x",
        status="planning",
        last_action_at="2026-05-30T10:00:00Z",
        last_action_kind="created",
    )
    assert state.subtype == "product"


def test_l1state_subtype_round_trip(tmp_path: Path) -> None:
    """write_l1_status + read_l1_status preserve subtype across persistence."""
    state = L1State(
        feature_slug="bonsai-refactor",
        status="planning",
        last_action_at="2026-05-30T10:00:00Z",
        last_action_kind="created",
        subtype="refactor",
    )
    l1.write_l1_status(state, tmp_path)
    read = l1.read_l1_status("bonsai-refactor", tmp_path)
    assert read is not None
    assert read.subtype == "refactor"


def test_l1state_subtype_bugfix_round_trip(tmp_path: Path) -> None:
    """write_l1_status + read_l1_status preserve subtype=bugfix (Gap 1)."""
    state = L1State(
        feature_slug="login-crash-fix",
        status="planning",
        last_action_at="2026-05-30T10:00:00Z",
        last_action_kind="created",
        subtype="bugfix",
    )
    l1.write_l1_status(state, tmp_path)
    read = l1.read_l1_status("login-crash-fix", tmp_path)
    assert read is not None
    assert read.subtype == "bugfix"


def test_l1state_validation_accepts_all_canonical_subtypes(tmp_path: Path) -> None:
    """All 5 canonical subtype values must round-trip without error."""
    for sub in ("product", "refactor", "bugfix", "spike", "chore"):
        state = L1State(
            feature_slug=f"feat-{sub}",
            status="planning",
            last_action_at="2026-05-30T10:00:00Z",
            last_action_kind="created",
            subtype=sub,
        )
        l1.write_l1_status(state, tmp_path)
        read = l1.read_l1_status(f"feat-{sub}", tmp_path)
        assert read is not None
        assert read.subtype == sub


def test_l1state_invalid_subtype_raises(tmp_path: Path) -> None:
    """Writing an unknown subtype raises MemoryError."""
    bad = L1State(
        feature_slug="x",
        status="planning",
        last_action_at="2026-05-30T10:00:00Z",
        last_action_kind="created",
        subtype="totally-fake-subtype",
    )
    with pytest.raises(MemoryError):
        l1.write_l1_status(bad, tmp_path)


# ── status.json forward compatibility ────────────────────────────────────────


def test_status_json_without_subtype_defaults_to_product(tmp_path: Path) -> None:
    """Legacy status.json without the `subtype` field reads as product."""
    l1_dir = tmp_path / ".claude" / "memory" / "L1" / "legacy-feature"
    l1_dir.mkdir(parents=True)
    legacy_payload = {
        "schema-version": 1,
        "feature-slug": "legacy-feature",
        "state": "planning",
        "last-action": "created",
        "last-action-at": "2026-04-01T10:00:00Z",
        "phase-lock": None,
    }
    (l1_dir / "status.json").write_text(json.dumps(legacy_payload), encoding="utf-8")

    state = l1.read_l1_status("legacy-feature", tmp_path)
    assert state is not None
    assert state.subtype == "product"


def test_status_json_with_invalid_subtype_falls_back_to_product(tmp_path: Path) -> None:
    """Garbage subtype value on disk reads as product (defensive)."""
    l1_dir = tmp_path / ".claude" / "memory" / "L1" / "corrupt-feature"
    l1_dir.mkdir(parents=True)
    payload = {
        "schema-version": 1,
        "feature-slug": "corrupt-feature",
        "state": "planning",
        "subtype": "definitely-not-a-subtype",
        "last-action": "created",
        "last-action-at": "2026-04-01T10:00:00Z",
        "phase-lock": None,
    }
    (l1_dir / "status.json").write_text(json.dumps(payload), encoding="utf-8")

    state = l1.read_l1_status("corrupt-feature", tmp_path)
    assert state is not None
    assert state.subtype == "product"


def test_current_subtype_helper_defaults_to_product_when_missing(tmp_path: Path) -> None:
    """current_subtype returns 'product' when status.json is absent."""
    assert l1.current_subtype("ghost", tmp_path) == "product"


def test_set_subtype_persists_to_status_json(tmp_path: Path) -> None:
    """set_subtype writes the field and is readable by current_subtype."""
    l1.set_subtype("feat", tmp_path, "refactor")
    assert l1.current_subtype("feat", tmp_path) == "refactor"


def test_set_subtype_persists_bugfix_to_status_json(tmp_path: Path) -> None:
    """set_subtype writes bugfix (Gap 1) and is readable by current_subtype."""
    l1.set_subtype("login-crash-fix", tmp_path, "bugfix")
    assert l1.current_subtype("login-crash-fix", tmp_path) == "bugfix"


def test_set_subtype_rejects_invalid_value(tmp_path: Path) -> None:
    """set_subtype gates on the enum."""
    with pytest.raises(MemoryError):
        l1.set_subtype("feat", tmp_path, "bogus")


# ── Intake template selection (Gap 1) ────────────────────────────────────────


def test_wave_a_bugfix_template_constant_points_at_bugfix_intake() -> None:
    """WAVE_A_BUGFIX_TEMPLATES selects the bugfix intake variant."""
    assert plan.WAVE_A_BUGFIX_TEMPLATES == (
        ("feature-intake-bugfix.template.md", "feature-intake.md"),
    )


def test_wave_a_template_constants_are_distinct() -> None:
    """Product / refactor / bugfix variants point at distinct files."""
    product = {src for src, _ in plan.WAVE_A_TEMPLATES}
    refactor = {src for src, _ in plan.WAVE_A_REFACTOR_TEMPLATES}
    bugfix = {src for src, _ in plan.WAVE_A_BUGFIX_TEMPLATES}
    # Refactor and bugfix each contain one entry distinct from product set.
    assert "feature-intake-refactor.template.md" in refactor
    assert "feature-intake-bugfix.template.md" in bugfix
    assert "feature-intake.template.md" in product
    assert refactor != bugfix
    assert product & refactor == set()
    assert product & bugfix == set()


def test_feature_intake_bugfix_template_exists_on_disk() -> None:
    """The bugfix intake template file must ship in templates/."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    template_path = (
        repo_root / "templates" / "feature-intake-bugfix.template.md"
    )
    assert template_path.is_file(), (
        f"templates/feature-intake-bugfix.template.md missing at {template_path} — "
        "engine.plan._run_waves_for_subtype would FileNotFoundError on a "
        "bugfix run."
    )


# ── hypothesis.yaml.wave_b_required round-trip (Gap 1) ───────────────────────


def test_hypothesis_wave_b_required_round_trip(tmp_forge_project: Path) -> None:
    """Wave B sub-question answer persists in hypothesis.yaml."""
    plan._persist_hypothesis_wave_b_required(
        "login-crash-fix", tmp_forge_project, True
    )
    assert (
        plan._read_hypothesis_wave_b_required("login-crash-fix", tmp_forge_project)
        is True
    )

    plan._persist_hypothesis_wave_b_required(
        "data-mapping-fix", tmp_forge_project, False
    )
    assert (
        plan._read_hypothesis_wave_b_required("data-mapping-fix", tmp_forge_project)
        is False
    )


def test_hypothesis_wave_b_required_missing_returns_none(
    tmp_forge_project: Path,
) -> None:
    """Absence of hypothesis.yaml reads as None (forces re-elicitation)."""
    assert (
        plan._read_hypothesis_wave_b_required("ghost-fix", tmp_forge_project)
        is None
    )


def test_hypothesis_wave_b_required_preserves_other_fields(
    tmp_forge_project: Path,
) -> None:
    """Writing wave_b_required does not clobber other hypothesis fields."""
    from engine.memory.l1 import read_hypothesis, write_hypothesis

    write_hypothesis(
        "some-fix",
        tmp_forge_project,
        {
            "schema-version": 1,
            "feature-slug": "some-fix",
            "subtype": "bugfix",
            "shape": "bugfix",
            "bug-ticket": "IN-37234",
            "confidence": 0.85,
        },
    )
    plan._persist_hypothesis_wave_b_required("some-fix", tmp_forge_project, True)

    data = read_hypothesis("some-fix", tmp_forge_project)
    assert data is not None
    assert data["wave_b_required"] is True
    assert data["bug-ticket"] == "IN-37234"
    assert data["confidence"] == 0.85
    assert data["subtype"] == "bugfix"


# ── check_no_behavior_change validator ───────────────────────────────────────


def _import_no_behavior_change_validator():
    """Import the standalone validator script as a module."""
    import importlib.util
    import sys as _sys

    repo_root = Path(__file__).resolve().parent.parent.parent
    script_path = repo_root / "validators" / "check_no_behavior_change.py"
    validators_dir = repo_root / "validators"
    if str(validators_dir) not in _sys.path:
        _sys.path.insert(0, str(validators_dir))

    spec = importlib.util.spec_from_file_location(
        "check_no_behavior_change",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_behavior_change_passes_when_subtype_is_product(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gate is inactive when subtype != refactor."""
    validator = _import_no_behavior_change_validator()
    # Seed an L1 with subtype=product.
    l1.set_subtype("some-feature", tmp_forge_project, "product")
    # Simulate git returning a test file in the diff.
    monkeypatch.setattr(
        validator,
        "_git_changed_files",
        lambda _root: ["shared/feature/x/src/commonTest/kotlin/FooTest.kt"],
    )

    result = validator.validate(
        tmp_forge_project, scope="feature", id="some-feature"
    )
    assert result["status"] == "pass"
    assert "não se aplica" in result["message"] or "product" in result["message"]


def test_no_behavior_change_passes_when_diff_avoids_tests(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refactor with diff that doesn't touch tests → pass."""
    validator = _import_no_behavior_change_validator()
    l1.set_subtype("refactor-feature", tmp_forge_project, "refactor")
    monkeypatch.setattr(
        validator,
        "_git_changed_files",
        lambda _root: [
            "shared/feature/auth/src/commonMain/kotlin/Auth.kt",
            "androidApp/feature/auth/build.gradle.kts",
        ],
    )

    result = validator.validate(
        tmp_forge_project, scope="feature", id="refactor-feature"
    )
    assert result["status"] == "pass"


def test_no_behavior_change_fails_when_test_files_modified(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refactor + test file in diff → fail with 3-paths block."""
    validator = _import_no_behavior_change_validator()
    l1.set_subtype("refactor-feature", tmp_forge_project, "refactor")
    monkeypatch.setattr(
        validator,
        "_git_changed_files",
        lambda _root: [
            "shared/feature/auth/src/commonMain/kotlin/Auth.kt",
            "shared/feature/auth/src/commonTest/kotlin/AuthTest.kt",
        ],
    )

    result = validator.validate(
        tmp_forge_project, scope="feature", id="refactor-feature"
    )
    assert result["status"] == "fail"
    paths = result.get("paths") or []
    assert len(paths) == 3, "discipline §1 demands exactly 3 paths"
    # Sanity: kinds are the canonical fix/revert/split set.
    kinds = sorted(p["kind"] for p in paths)
    assert kinds == ["fix", "revert", "split"]


def test_no_behavior_change_recognises_multiple_test_path_segments(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """androidUnitTest / __tests__ / iosX64Test paths also trip the gate."""
    validator = _import_no_behavior_change_validator()
    l1.set_subtype("refactor-feature", tmp_forge_project, "refactor")
    monkeypatch.setattr(
        validator,
        "_git_changed_files",
        lambda _root: [
            "androidApp/feature/x/src/androidUnitTest/kotlin/SomethingTest.kt",
        ],
    )
    result = validator.validate(
        tmp_forge_project, scope="feature", id="refactor-feature"
    )
    assert result["status"] == "fail"


def test_no_behavior_change_passes_when_no_diff_at_all(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refactor with empty diff is a no-op pass (Wave E pre-commit dry-run)."""
    validator = _import_no_behavior_change_validator()
    l1.set_subtype("refactor-feature", tmp_forge_project, "refactor")
    monkeypatch.setattr(validator, "_git_changed_files", lambda _root: [])

    result = validator.validate(
        tmp_forge_project, scope="feature", id="refactor-feature"
    )
    assert result["status"] == "pass"
