"""Resume-from-checkpoint tests for ``engine.plan`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: per-subcommand ``_PlanCheckpoint`` dataclass
following ``_InitCheckpoint`` template (``engine/init.py:100-108``).
Lives in this module — NO import from ``engine.qa.checkpoint``.

plan expoe 10 callsites interativos (ask em readiness-not-ready 3-paths,
ask em done-feature 4-paths, ask em subtype-confirmation, ask em
bugfix-wave-b sub-question, ask_text em slug + extension-slug + task-count,
ask em continuar/pausar a cada wave). O resume cobre o cenario canonico
em que o host pausou no ask_text de slug e re-invoca com response no disco.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (action=add-new, reuse_path=init-pattern)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import plan
from engine.ui import question


# ── Smoke — dataclass + helpers existem (add-new) ────────────────────────────


def test_plan_checkpoint_dataclass_exists() -> None:
    """_PlanCheckpoint dataclass surface must mirror _InitCheckpoint shape."""
    cp_cls = getattr(plan, "_PlanCheckpoint", None)
    assert cp_cls is not None, "_PlanCheckpoint not declared in engine.plan"
    cp = cp_cls(
        step="step-elicit-slug",
        at="2026-06-10T00:00:00Z",
        project_root="/tmp/foo",
    )
    assert cp.step == "step-elicit-slug"
    assert getattr(cp, "intent_id", "<missing>") is None
    assert getattr(cp, "feature_slug", "<missing>") is None
    assert getattr(cp, "wave", "<missing>") is None
    assert getattr(cp, "ambiguity_id", "<missing>") is None


def test_plan_save_load_clear_roundtrip(tmp_forge_project: Path) -> None:
    """_save/_load/_clear_plan_checkpoint sao idempotentes per outcome C."""
    save = getattr(plan, "_save_plan_checkpoint", None)
    load = getattr(plan, "_load_plan_checkpoint", None)
    clear = getattr(plan, "_clear_plan_checkpoint", None)
    assert save is not None, "_save_plan_checkpoint missing"
    assert load is not None, "_load_plan_checkpoint missing"
    assert clear is not None, "_clear_plan_checkpoint missing"

    cp = plan._PlanCheckpoint(
        step="step-wave-d",
        at="2026-06-10T00:00:00Z",
        project_root=str(tmp_forge_project),
        intent_id="mno-321",
        feature_slug="lembrete-rega",
        wave="D",
        ambiguity_id="readiness-not-ready",
    )
    save(cp)
    loaded = load(tmp_forge_project)
    assert isinstance(loaded, dict)
    assert loaded.get("step") == "step-wave-d"
    assert loaded.get("intent-id") == "mno-321"
    assert loaded.get("feature-slug") == "lembrete-rega"
    assert loaded.get("wave") == "D"
    assert loaded.get("ambiguity-id") == "readiness-not-ready"

    clear(tmp_forge_project)
    assert load(tmp_forge_project) is None


# ── Comportamento — resume consome response do slug, nao re-prompta ─────────


def _seed_workflow_config(project_root: Path) -> None:
    """plan.run exige workflow-config.yaml — escreve um minimo."""
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-plan-resume\n",
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
         value="!!!" — slug invalido pra forcar SystemExit antes das
         waves (evita simular template dir, etc.).
      3. Invocacao B (este test): plan.run carrega checkpoint, descobre
         intent_id; ``question.ask_text`` consome response, retorna o
         valor; run levanta SystemExit por slug invalido.
      4. Checkpoint pode permanecer (exit forensic em SystemExit) — test
         apenas valida que a response foi consumida sem re-prompt.

    Escolha de slug invalido evita ter de preparar templates + L1 state.
    Cobertura dos prompts internos sai via test_commands_plan.py + integration.
    """
    _seed_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Stage 1 — calcula o intent-id deterministico da pergunta de slug.
    # Argumentos seguem _elicit_slug em engine/plan.py.
    intent_id = question._stable_intent_id(
        "ask_text",
        "Qual o slug da feature? (kebab-case, ex.: lembrete-rega)",
        None,
        extra={
            "default": None,
            "min-selected": None,
            "validator-hint": (
                "kebab-case lowercase, 2..50 chars, deve começar com letra."
            ),
        },
    )

    # Stage 2 — host escreveu response.json + checkpoint do plan.
    # value invalido (caracteres especiais) → _elicit_slug aceita via
    # question.ask_text (validator passa porque response vem do disco
    # e nao re-valida); mas plan.run downstream rejeita slug invalido
    # via _is_valid_slug check, levantando SystemExit. Para forçar a
    # rota mais simples, escolhemos slug valido mas inexistente, e
    # confiamos que o run completa minimo até o ponto que prova consumo
    # da response.
    valid_slug = "ghost-feature-plan"
    state_dir = tmp_forge_project / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    response_payload = {
        "schema-version": 1,
        "intent-id": intent_id,
        "value": valid_slug,
        "responded-at": "2026-06-10T00:01:00Z",
    }
    (state_dir / "forge-response.json").write_text(
        json.dumps(response_payload), encoding="utf-8"
    )
    cp = plan._PlanCheckpoint(
        step="step-elicit-slug",
        at="2026-06-10T00:00:30Z",
        project_root=str(tmp_forge_project),
        intent_id=intent_id,
        feature_slug=None,
    )
    plan._save_plan_checkpoint(cp)

    # Sanity — checkpoint + response no disco antes de rodar.
    assert plan._load_plan_checkpoint(tmp_forge_project) is not None
    assert (state_dir / "forge-response.json").exists()

    # Stage 3 — invoca plan.run([]). question.ask_text deve consumir o
    # response do slug; run prossegue ate o primeiro prompt SEM response
    # no disco (que sera o ask de continuar/pausar na Wave A) e ai
    # levanta um novo PausedForInputError com intent-id DIFERENTE do
    # slug-ask. Isso prova que: (a) o slug-response foi consumido (nao
    # houve re-prompt do mesmo intent-id) e (b) o handler avancou pra
    # uma pergunta nova.
    advanced_past_slug = False
    try:
        plan.run([])
    except question.PausedForInputError as exc:
        # Pausou de novo, mas com intent-id NOVO — o handler avancou
        # alem do slug-elicit.
        new_intent_id = exc.intent.get("intent-id")
        assert new_intent_id != intent_id, (
            f"plan.run re-pausou no mesmo intent-id ({intent_id}) — "
            "response do slug nao foi consumida"
        )
        advanced_past_slug = True
    except SystemExit:
        # Caminho alternativo: run pode levantar SystemExit antes do
        # primeiro prompt novo (ex.: phase-lock falha). Tambem prova
        # que avancou alem do slug-ask.
        advanced_past_slug = True

    assert advanced_past_slug, (
        "plan.run nao saiu/pausou apos consumir o slug response"
    )

    # Resume contract: forge-response.json do slug-ask deve ter sido
    # consumido. O novo PausedForInputError pode ter ESCRITO um pending
    # diferente em disco — mas o RESPONSE original foi limpo por
    # _clear_state ao consumir match.
    assert not (state_dir / "forge-response.json").exists(), (
        "response file should be consumed/cleared after successful resume"
    )
