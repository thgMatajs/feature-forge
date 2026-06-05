"""Unit tests — Gap 9 Cena 1 extension branch in engine.plan.

Wave 2 coverage. Wave 1 already covered L1State + validator in
`test_extension_feature.py`; this file focuses on the engine.plan entry
helpers introduced in Wave 2:

- ``_default_extension_slug`` — heuristic ``{parent}-extension``
- ``_import_parent_context`` — read parent L1 + key artefacts, returns
  baseline dict for context-pack seeding
- ``_create_extension_l1`` — writes child status.json + hypothesis.yaml
  in lockstep, with extends-feature + parent-feature pointing at parent
- ``_handle_done_feature_branch`` — Cena 1 4-paths dispatcher (Retomar /
  Nova / Estender / Abortar); only active when parent.state == "done".

Wave A skipping logic for extension features (conductor inference of
delta-only context-pack) lives in agents/planning-conductor.md and is
NOT exercised here (docs-only — covered in Wave 2 commit C8).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine import plan
from engine.memory import l1


# ── Helpers ──────────────────────────────────────────────────────────────────


def _seed_parent_done(
    project_root: Path,
    slug: str,
    *,
    shipped_at: str | None = "2026-05-28T18:00:00Z",
    hypothesis: dict | None = None,
) -> None:
    """Write a parent L1 in state=done with optional shipped-at + hypothesis.

    Mirrors how a real shipped feature looks on disk: status.json with
    state=done, hypothesis.yaml with the parent's structural read, and
    a stub feature folder (so _import_parent_context can resolve it).
    """
    l1_dir = project_root / ".claude" / "memory" / "L1" / slug
    l1_dir.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "schema-version": 1,
        "feature-slug": slug,
        "state": "done",
        "subtype": "product",
        "last-action": "shipped",
        "last-action-at": "2026-05-28T18:00:00Z",
        "phase-lock": None,
        "extends-feature": None,
        "parent-feature": None,
    }
    if shipped_at is not None:
        payload["shipped-at"] = shipped_at
    (l1_dir / "status.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    if hypothesis is not None:
        (l1_dir / "hypothesis.yaml").write_text(
            yaml.safe_dump(hypothesis), encoding="utf-8"
        )
    # Stub feature folder so _import_parent_context can resolve relative path.
    feature_dir = (
        project_root
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    feature_dir.mkdir(parents=True, exist_ok=True)


# ── _default_extension_slug ──────────────────────────────────────────────────


def test_default_extension_slug_appends_extension_suffix() -> None:
    """Heuristic default is ``{parent}-extension``."""
    assert plan._default_extension_slug("lembrete-rega") == "lembrete-rega-extension"


def test_default_extension_slug_works_with_short_slug() -> None:
    """No special-casing for short slugs — same suffix."""
    assert plan._default_extension_slug("auth") == "auth-extension"


# ── _import_parent_context ───────────────────────────────────────────────────


def test_import_parent_context_happy(tmp_forge_project: Path) -> None:
    """Reads parent state + shipped-at + hypothesis + feature dir."""
    _seed_parent_done(
        tmp_forge_project,
        "lembrete-rega",
        shipped_at="2026-05-28T18:00:00Z",
        hypothesis={
            "schema-version": 1,
            "feature-slug": "lembrete-rega",
            "shape": "list+detail",
            "screens": ["list", "detail", "create"],
            "subtype": "product",
        },
    )
    ctx = plan._import_parent_context("lembrete-rega", tmp_forge_project)
    assert ctx["parent-slug"] == "lembrete-rega"
    assert ctx["parent-state"] == "done"
    assert ctx["parent-shipped-at"] == "2026-05-28T18:00:00Z"
    assert isinstance(ctx["parent-hypothesis"], dict)
    assert ctx["parent-hypothesis"]["shape"] == "list+detail"
    assert ctx["parent-feature-dir"] is not None
    assert "lembrete-rega" in ctx["parent-feature-dir"]


def test_import_parent_context_missing_parent_returns_nulls(
    tmp_forge_project: Path,
) -> None:
    """Parent absent on disk → all fields None except parent-slug."""
    ctx = plan._import_parent_context("does-not-exist", tmp_forge_project)
    assert ctx["parent-slug"] == "does-not-exist"
    assert ctx["parent-state"] is None
    assert ctx["parent-shipped-at"] is None
    assert ctx["parent-hypothesis"] is None
    assert ctx["parent-feature-dir"] is None


def test_import_parent_context_missing_shipped_at(tmp_forge_project: Path) -> None:
    """Parent done but no shipped-at → field is None, others read normally."""
    _seed_parent_done(
        tmp_forge_project,
        "auth-login",
        shipped_at=None,
        hypothesis={"shape": "form", "subtype": "product"},
    )
    ctx = plan._import_parent_context("auth-login", tmp_forge_project)
    assert ctx["parent-state"] == "done"
    assert ctx["parent-shipped-at"] is None
    assert ctx["parent-hypothesis"]["shape"] == "form"


# ── _create_extension_l1 ─────────────────────────────────────────────────────


def test_create_extension_l1_writes_status_and_hypothesis(
    tmp_forge_project: Path,
) -> None:
    """Lockstep write of extends-feature + parent-feature on both files."""
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    child_state = plan._create_extension_l1(
        "lembrete-rega", "lembrete-rega-push", tmp_forge_project
    )
    # status.json
    assert child_state.extends_feature == "lembrete-rega"
    assert child_state.parent_feature == "lembrete-rega"
    assert child_state.status == "planning"
    assert child_state.subtype == "product"
    # Round-trip via reader.
    read = l1.read_l1_status("lembrete-rega-push", tmp_forge_project)
    assert read is not None
    assert read.extends_feature == "lembrete-rega"
    assert read.parent_feature == "lembrete-rega"
    # hypothesis.yaml
    hyp = l1.read_hypothesis("lembrete-rega-push", tmp_forge_project)
    assert hyp is not None
    assert hyp["extends-feature"] == "lembrete-rega"
    assert hyp["parent-feature"] == "lembrete-rega"
    assert hyp["shape"] == "extension"
    assert hyp["subtype"] == "product"


def test_create_extension_l1_no_orphan_status_on_hypothesis_failure(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """D-003: OSError em write_hypothesis NÃO deve deixar status.json órfão.

    Pré-fix: status.json era escrito ANTES de hypothesis.yaml — se o segundo
    write quebrasse, child L1 ficava com state=planning + extends-feature
    no disco sem hypothesis.yaml, e resume futuro entrava em estado
    incoerente.

    Pós-fix: hypothesis.yaml vai primeiro como planning artefact;
    status.json vai por último como commit point. OSError em write_hypothesis
    aborta tudo — nada persistido (sem status.json órfão).
    """
    _seed_parent_done(tmp_forge_project, "lembrete-rega")

    def _boom(*args, **kwargs):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr("engine.plan.write_hypothesis", _boom)

    with pytest.raises(OSError, match="disk full"):
        plan._create_extension_l1(
            "lembrete-rega", "lembrete-rega-push", tmp_forge_project
        )

    # Child status.json deve estar ausente — sem órfão de planning.
    child_status_path = (
        tmp_forge_project
        / ".claude"
        / "memory"
        / "L1"
        / "lembrete-rega-push"
        / "status.json"
    )
    assert not child_status_path.exists(), (
        "status.json órfão criado apesar de write_hypothesis falhar — "
        "ordem write_hypothesis/write_l1_status quebrada"
    )


def test_create_extension_l1_rejects_self_loop(tmp_forge_project: Path) -> None:
    """child slug == parent slug raises (defensive — EXT-003)."""
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    with pytest.raises(ValueError, match="cannot equal parent slug"):
        plan._create_extension_l1(
            "lembrete-rega", "lembrete-rega", tmp_forge_project
        )


def test_create_extension_l1_rejects_missing_parent(tmp_forge_project: Path) -> None:
    """Parent has no status.json → raises (caller must seed first)."""
    with pytest.raises(ValueError, match="no status.json"):
        plan._create_extension_l1(
            "ghost-parent", "ghost-parent-ext", tmp_forge_project
        )


def test_create_extension_l1_rejects_empty_slugs(tmp_forge_project: Path) -> None:
    """Empty parent or child slug raises (defensive)."""
    with pytest.raises(ValueError, match="non-empty"):
        plan._create_extension_l1("", "child", tmp_forge_project)
    with pytest.raises(ValueError, match="non-empty"):
        plan._create_extension_l1("parent", "", tmp_forge_project)


def _seed_parent_state(project_root: Path, slug: str, state: str) -> None:
    """Write parent status.json com state arbitrário (não-done) — W-005 setup.

    Usado pra exercitar o guard de EXT-002 no nível do helper write-time.
    """
    l1_dir = project_root / ".claude" / "memory" / "L1" / slug
    l1_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema-version": 1,
        "feature-slug": slug,
        "state": state,
        "subtype": "product",
        "last-action": "seeded",
        "last-action-at": "2026-06-03T10:00:00Z",
        "phase-lock": None,
    }
    (l1_dir / "status.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def test_create_extension_l1_rejects_parent_in_planning(
    tmp_forge_project: Path,
) -> None:
    """W-005 (EXT-002 write-time guard): parent em state=planning → ValueError."""
    _seed_parent_state(tmp_forge_project, "still-cooking", "planning")
    with pytest.raises(ValueError, match="EXT-002"):
        plan._create_extension_l1(
            "still-cooking", "premature-ext", tmp_forge_project
        )


def test_create_extension_l1_rejects_parent_in_implementing(
    tmp_forge_project: Path,
) -> None:
    """W-005 (EXT-002 write-time guard): parent em state=implementing → ValueError."""
    _seed_parent_state(tmp_forge_project, "mid-flight", "implementing")
    with pytest.raises(ValueError, match="EXT-002"):
        plan._create_extension_l1(
            "mid-flight", "mid-flight-ext", tmp_forge_project
        )


def test_create_extension_l1_rejects_parent_in_verifying(
    tmp_forge_project: Path,
) -> None:
    """W-005 (EXT-002 write-time guard): parent em state=verifying → ValueError.

    Mensagem de erro deve citar o estado real e o código EXT-002 pra
    quem ler stack trace ter pista direta de qual invariante quebrou.
    """
    _seed_parent_state(tmp_forge_project, "almost-done", "verifying")
    with pytest.raises(ValueError) as exc_info:
        plan._create_extension_l1(
            "almost-done", "almost-done-ext", tmp_forge_project
        )
    msg = str(exc_info.value)
    assert "EXT-002" in msg
    assert "verifying" in msg
    assert "almost-done" in msg


# ── _handle_done_feature_branch (4-caminhos integration) ─────────────────────


def test_handle_done_feature_branch_extend_happy(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """User picks caminho 3 (Estender) with default slug — extension created."""
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    # Mock interactive prompts: choice "3" then accept default slug
    # (empty input → default), no duplicate path needed.
    answers = iter(["3", ""])  # "3" → ask_text returns default on empty
    monkeypatch.setattr(
        "engine.plan.question.ask",
        lambda *a, **kw: next(answers),
    )
    monkeypatch.setattr(
        "engine.plan.question.ask_text",
        lambda *a, **kw: kw.get("default", ""),
    )

    resolved = plan._handle_done_feature_branch(
        "lembrete-rega", tmp_forge_project
    )
    assert resolved == "lembrete-rega-extension"
    # Child L1 exists with extends-feature pointing at parent.
    child = l1.read_l1_status("lembrete-rega-extension", tmp_forge_project)
    assert child is not None
    assert child.extends_feature == "lembrete-rega"


def test_handle_done_feature_branch_extend_custom_slug(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """User picks caminho 3 and customizes derived slug."""
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    monkeypatch.setattr("engine.plan.question.ask", lambda *a, **kw: "3")
    monkeypatch.setattr(
        "engine.plan.question.ask_text",
        lambda *a, **kw: "lembrete-rega-push",
    )

    resolved = plan._handle_done_feature_branch(
        "lembrete-rega", tmp_forge_project
    )
    assert resolved == "lembrete-rega-push"
    child = l1.read_l1_status("lembrete-rega-push", tmp_forge_project)
    assert child is not None
    assert child.extends_feature == "lembrete-rega"


def test_handle_done_feature_branch_nova_returns_none(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """Caminho 2 (Nova) → returns None, no child L1 written."""
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    monkeypatch.setattr("engine.plan.question.ask", lambda *a, **kw: "2")
    resolved = plan._handle_done_feature_branch(
        "lembrete-rega", tmp_forge_project
    )
    assert resolved is None
    # Parent state untouched.
    parent = l1.read_l1_status("lembrete-rega", tmp_forge_project)
    assert parent is not None
    assert parent.status == "done"


def test_handle_done_feature_branch_abortar_returns_none(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """Caminho 4 (Abortar) → returns None, nothing written."""
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    monkeypatch.setattr("engine.plan.question.ask", lambda *a, **kw: "4")
    resolved = plan._handle_done_feature_branch(
        "lembrete-rega", tmp_forge_project
    )
    assert resolved is None


def test_handle_done_feature_branch_retomar_flips_parent_to_planning(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """Caminho 1 (Retomar) → parent state flipped back to planning."""
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    monkeypatch.setattr("engine.plan.question.ask", lambda *a, **kw: "1")
    resolved = plan._handle_done_feature_branch(
        "lembrete-rega", tmp_forge_project
    )
    assert resolved == "lembrete-rega"
    parent = l1.read_l1_status("lembrete-rega", tmp_forge_project)
    assert parent is not None
    assert parent.status == "planning"


def test_handle_done_feature_branch_inactive_on_non_done(
    tmp_forge_project: Path,
) -> None:
    """Parent in state != done → no-op (returns parent slug, no prompt)."""
    # Seed parent in state=implementing instead of done.
    l1_dir = (
        tmp_forge_project / ".claude" / "memory" / "L1" / "in-flight-feature"
    )
    l1_dir.mkdir(parents=True, exist_ok=True)
    (l1_dir / "status.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "feature-slug": "in-flight-feature",
                "state": "implementing",
                "subtype": "product",
                "last-action": "wave-b-acknowledged",
                "last-action-at": "2026-06-03T08:00:00Z",
                "phase-lock": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # No monkeypatch needed — function should NOT prompt.
    resolved = plan._handle_done_feature_branch(
        "in-flight-feature", tmp_forge_project
    )
    assert resolved == "in-flight-feature"


def test_handle_done_feature_branch_duplicate_slug_abort(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """User picks caminho 3, customizes to duplicate slug, then aborts (path b).

    Validates the 3-caminhos duplicate-handling branch returns None when
    user picks path b (abortar) at the duplicate gate.
    """
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    # Seed an existing L1 the user will accidentally collide with.
    other_dir = (
        tmp_forge_project / ".claude" / "memory" / "L1" / "lembrete-rega-push"
    )
    other_dir.mkdir(parents=True, exist_ok=True)
    (other_dir / "status.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "feature-slug": "lembrete-rega-push",
                "state": "planning",
                "subtype": "product",
                "last-action": "plan-started",
                "last-action-at": "2026-06-03T07:00:00Z",
                "phase-lock": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # First ask: choice "3" (Estender). Then ask_three_paths returns "b"
    # (Abortar) at the duplicate gate.
    ask_calls = iter(["3", "b"])
    monkeypatch.setattr("engine.plan.question.ask", lambda *a, **kw: next(ask_calls))
    monkeypatch.setattr(
        "engine.plan.question.ask_text",
        lambda *a, **kw: "lembrete-rega-push",
    )
    # ask_three_paths under the hood calls ask() — the second next() above
    # captures it. The internal options pass-through doesn't matter here.
    monkeypatch.setattr(
        "engine.plan.question.ask_three_paths",
        lambda *a, **kw: "b",
    )

    resolved = plan._handle_done_feature_branch(
        "lembrete-rega", tmp_forge_project
    )
    assert resolved is None
    # Pre-existing sibling untouched.
    sibling = l1.read_l1_status("lembrete-rega-push", tmp_forge_project)
    assert sibling is not None
    assert sibling.status == "planning"  # not flipped


def test_handle_done_feature_branch_duplicate_slug_abort_message_interpolates_candidate(
    tmp_forge_project: Path, monkeypatch, capsys
) -> None:
    """D-001: abort message no caminho duplicate-slug interpola o slug digitado.

    Pré-fix: a mensagem usava string normal ('{slug}') + variável inexistente.
    User via texto literal '{slug}' em vez do slug duplicado que digitou.
    Pós-fix: f-string com 'candidate' (o slug que o user efetivamente tentou)
    pra que a sugestão 'Use forge undo <slug>' seja acionável.
    """
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    # Seed um L1 existente que vai colidir com o slug derivado escolhido.
    other_dir = (
        tmp_forge_project / ".claude" / "memory" / "L1" / "lembrete-rega-push"
    )
    other_dir.mkdir(parents=True, exist_ok=True)
    (other_dir / "status.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "feature-slug": "lembrete-rega-push",
                "state": "planning",
                "subtype": "product",
                "last-action": "plan-started",
                "last-action-at": "2026-06-03T07:00:00Z",
                "phase-lock": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    ask_calls = iter(["3", "b"])  # 3 = Estender; b = Abortar no dup gate
    monkeypatch.setattr("engine.plan.question.ask", lambda *a, **kw: next(ask_calls))
    monkeypatch.setattr(
        "engine.plan.question.ask_text",
        lambda *a, **kw: "lembrete-rega-push",
    )
    monkeypatch.setattr(
        "engine.plan.question.ask_three_paths",
        lambda *a, **kw: "b",
    )

    resolved = plan._handle_done_feature_branch(
        "lembrete-rega", tmp_forge_project
    )
    assert resolved is None

    captured = capsys.readouterr()
    # Mensagem deve citar o slug duplicado real (candidate), não o literal '{slug}'.
    assert "forge undo lembrete-rega-push" in captured.out
    assert "{slug}" not in captured.out
    assert "{candidate}" not in captured.out


def test_handle_done_feature_branch_duplicate_slug_retry(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """User picks caminho 3, duplicate collision, picks path a (try again)."""
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    other_dir = (
        tmp_forge_project / ".claude" / "memory" / "L1" / "lembrete-rega-push"
    )
    other_dir.mkdir(parents=True, exist_ok=True)
    (other_dir / "status.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "feature-slug": "lembrete-rega-push",
                "state": "planning",
                "subtype": "product",
                "last-action": "plan-started",
                "last-action-at": "2026-06-03T07:00:00Z",
                "phase-lock": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("engine.plan.question.ask", lambda *a, **kw: "3")
    # ask_text returns colliding slug first, then a fresh one.
    slug_answers = iter(["lembrete-rega-push", "lembrete-rega-widget"])
    monkeypatch.setattr(
        "engine.plan.question.ask_text",
        lambda *a, **kw: next(slug_answers),
    )
    monkeypatch.setattr(
        "engine.plan.question.ask_three_paths",
        lambda *a, **kw: "a",  # try again
    )

    resolved = plan._handle_done_feature_branch(
        "lembrete-rega", tmp_forge_project
    )
    assert resolved == "lembrete-rega-widget"
    child = l1.read_l1_status("lembrete-rega-widget", tmp_forge_project)
    assert child is not None
    assert child.extends_feature == "lembrete-rega"


def test_handle_done_feature_branch_extend_self_loop_rejected(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """User tries to use parent slug as derived slug → loops back.

    The internal guard rejects self-loop and re-prompts. On the second
    attempt the user provides a fresh slug.
    """
    _seed_parent_done(tmp_forge_project, "lembrete-rega")
    monkeypatch.setattr("engine.plan.question.ask", lambda *a, **kw: "3")
    slug_answers = iter(["lembrete-rega", "lembrete-rega-fresh"])
    monkeypatch.setattr(
        "engine.plan.question.ask_text",
        lambda *a, **kw: next(slug_answers),
    )

    resolved = plan._handle_done_feature_branch(
        "lembrete-rega", tmp_forge_project
    )
    assert resolved == "lembrete-rega-fresh"
    child = l1.read_l1_status("lembrete-rega-fresh", tmp_forge_project)
    assert child is not None
    assert child.extends_feature == "lembrete-rega"
