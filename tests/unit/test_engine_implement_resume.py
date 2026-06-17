"""Resume-from-checkpoint tests for ``engine.implement`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: per-subcommand ``_ImplementCheckpoint`` dataclass
following ``_InitCheckpoint`` template (``engine/init.py:100-108``).
Lives in this module — NO import from ``engine.qa.checkpoint``.

implement expoe 7 callsites interativos (ask_text de slug, confirm de
plan-mode, ask_three_paths de out-of-scope e qa.auto-run, ask_text de
finding/allowed-files, confirm bonus). O resume cobre o cenario
canonico em que o host pausou no slug ask_text e re-invoca com response
no disco.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (action=add-new, reuse_path=init-pattern)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import implement
from engine.ui import question


# ── Smoke — dataclass + helpers existem (add-new) ────────────────────────────


def test_implement_checkpoint_dataclass_exists() -> None:
    """_ImplementCheckpoint dataclass surface must mirror _InitCheckpoint shape."""
    cp_cls = getattr(implement, "_ImplementCheckpoint", None)
    assert cp_cls is not None, "_ImplementCheckpoint not declared in engine.implement"
    cp = cp_cls(
        step="step-elicit-slug",
        at="2026-06-10T00:00:00Z",
        project_root="/tmp/foo",
    )
    assert cp.step == "step-elicit-slug"
    assert getattr(cp, "intent_id", "<missing>") is None
    assert getattr(cp, "feature_slug", "<missing>") is None
    assert getattr(cp, "task_id", "<missing>") is None


def test_implement_save_load_clear_roundtrip(tmp_forge_project: Path) -> None:
    """_save/_load/_clear_implement_checkpoint sao idempotentes per outcome C."""
    save = getattr(implement, "_save_implement_checkpoint", None)
    load = getattr(implement, "_load_implement_checkpoint", None)
    clear = getattr(implement, "_clear_implement_checkpoint", None)
    assert save is not None, "_save_implement_checkpoint missing"
    assert load is not None, "_load_implement_checkpoint missing"
    assert clear is not None, "_clear_implement_checkpoint missing"

    cp = implement._ImplementCheckpoint(
        step="step-post-slug",
        at="2026-06-10T00:00:00Z",
        project_root=str(tmp_forge_project),
        intent_id="jkl-987",
        feature_slug="lembrete-rega",
        task_id="TASK-0001",
    )
    save(cp)
    loaded = load(tmp_forge_project)
    assert isinstance(loaded, dict)
    assert loaded.get("step") == "step-post-slug"
    assert loaded.get("intent-id") == "jkl-987"
    assert loaded.get("feature-slug") == "lembrete-rega"
    assert loaded.get("task-id") == "TASK-0001"

    clear(tmp_forge_project)
    assert load(tmp_forge_project) is None


# ── Comportamento — resume consome response do slug, nao re-prompta ─────────


def _seed_workflow_config(project_root: Path) -> None:
    """implement.run exige workflow-config.yaml — escreve um minimo."""
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-implement-resume\n",
        encoding="utf-8",
    )


def test_resume_from_checkpoint(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cenario canonico de resume — checkpoint do slug-ask + response.json correspondente.

    Sequencia simulada:
      1. Invocacao A pausou no ``ask_text`` de slug (gravou pending +
         checkpoint com intent_id da pergunta canonica).
      2. Host escreveu ``forge-response.json`` com mesmo intent_id +
         value="ghost-feature".
      3. Invocacao B (este test): implement.run carrega checkpoint,
         descobre intent_id; ``question.ask_text`` consome response,
         retorna "ghost-feature" sem raise; run prossegue, descobre
         que a feature nao existe no disco, retorna exit 4 (feature
         missing).
      4. Checkpoint apagado apos clean exit (mesmo em exit 4 — exit-4 e
         hard fail estrutural, nao invalid-response).

    Test escolhe um slug que nao existe pra disparar exit 4 logo apos
    o slug ask — evita simular plan handoff + tasks + readiness. O
    contract de resume requer apenas: response consumida pelo
    ``question.ask_text`` E checkpoint limpo no exit.
    """
    _seed_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Task 0.7b — pin host: intent-file so question.ask_text delegate
    # writes/reads against .claude/forge/state/ (v1.3 sub-namespace).
    forge_dir = tmp_forge_project / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "host: intent-file\n", encoding="utf-8"
    )
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()

    # Stage 1 — calcula o intent-id deterministico da pergunta de slug.
    # Argumentos seguem _elicit_slug em engine/implement.py.
    # Task 0.7b: o delegate roda o intent via host adapter, que passa
    # ``options={}`` para o ``_ask_loop`` em ``ask_text``. Pra reproduzir
    # bit-a-bit o intent-id que o adapter calcula, usamos a mesma forma.
    intent_id = question._stable_intent_id(
        "ask_text",
        "Qual feature implementar? (slug kebab-case)",
        {},
        extra={
            "default": None,
            "min-selected": None,
            "validator-hint": "kebab-case lowercase, 2..50 chars.",
        },
    )

    # Stage 2 — host escreveu response.json + checkpoint do implement.
    state_dir = tmp_forge_project / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    response_payload = {
        "schema-version": 1,
        "intent-id": intent_id,
        "value": "ghost-feature",
        "responded-at": "2026-06-10T00:01:00Z",
    }
    (state_dir / "forge-response.json").write_text(
        json.dumps(response_payload), encoding="utf-8"
    )
    cp = implement._ImplementCheckpoint(
        step="step-elicit-slug",
        at="2026-06-10T00:00:30Z",
        project_root=str(tmp_forge_project),
        intent_id=intent_id,
        feature_slug=None,
    )
    implement._save_implement_checkpoint(cp)

    # Sanity — checkpoint + response no disco antes de rodar.
    assert implement._load_implement_checkpoint(tmp_forge_project) is not None
    assert (state_dir / "forge-response.json").exists()

    # Stage 3 — invoca implement.run([]). question.ask_text deve consumir
    # o response, voltar "ghost-feature", run descobre que feature nao
    # existe e retorna 4 (feature missing).
    rc = implement.run([])

    assert rc == 4, f"unexpected exit code from implement.run: {rc}"

    # Task 0.7b — CR-002 invariant: state files MUST remain on disk
    # after happy-path consume. cli.py finally block performs the
    # terminal cleanup at handler exit, preserving forensic inspection.
    assert (state_dir / "forge-response.json").exists(), (
        "response file must survive happy-path consume (CR-002)"
    )

    # Checkpoint deve ser apagado apos run completar (exit 4 = clean
    # structural fail, nao invalid-response).
    assert implement._load_implement_checkpoint(tmp_forge_project) is None, (
        "checkpoint should be cleared after exit 4 (feature missing)"
    )
