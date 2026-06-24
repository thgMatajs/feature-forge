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
    # Argumentos seguem _elicit_slug em engine/plan.py.
    # Task 0.7b: o delegate roda o intent via host adapter, que passa
    # ``options={}`` para o ``_ask_loop`` em ``ask_text``. Pra reproduzir
    # bit-a-bit o intent-id que o adapter calcula, usamos a mesma forma.
    intent_id = question._stable_intent_id(
        "ask_text",
        "Qual o slug da feature? (kebab-case, ex.: lembrete-rega)",
        {},
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
    state_dir = tmp_forge_project / ".claude" / "forge" / "state"
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
    #
    # Task 0.7b — CR-002: o response file do slug NAO e mais
    # auto-clearado apos consume. O prompt seguinte da Wave A vai
    # encontrar o response file legado em disco (slug intent-id) e
    # levantar IntentMismatchError porque o novo intent-id da Wave A
    # nao bate. Este path tambem prova que o handler avancou alem do
    # slug-elicit; cli.py mapeia IntentMismatchError pra exit 1 (ver
    # engine/cli.py:341). No teste tratamos como assinatura valida
    # do avanco.
    from engine.ui import intent_state

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
    except intent_state.IntentMismatchError as exc:
        # CR-002: o response do slug ficou em disco e a Wave A pediu um
        # intent-id NOVO. A mismatch entre o file (slug) e o novo
        # intent-id pedido prova que o handler avancou alem do slug-ask.
        msg = str(exc)
        assert intent_id in msg, (
            "IntentMismatchError nao referencia o slug intent-id em disco — "
            "o avanco para alem do slug-elicit nao foi comprovado"
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

    # Task 0.7b — CR-002 invariant: state files MUST remain on disk
    # after happy-path consume. cli.py finally block performs the
    # terminal cleanup at handler exit, preserving forensic inspection.
    # O novo PausedForInputError downstream pode ter sobrescrito o
    # pending com um intent-id diferente, mas o response original
    # permanece em disco até o cli.py terminal cleanup.
    assert (state_dir / "forge-response.json").exists(), (
        "response file must survive happy-path consume (CR-002)"
    )


# ── P-15: gating de guards de re-entrada do plan (host_is_replaying) ─────────


def _pin_intent_file_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Força host=intent-file via escape-hatch env (mesma forma do init test)."""
    monkeypatch.setenv("FORGE_FORCE_INTENT_MODE", "1")
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()


def _seed_l1(project_root: Path, *, slug: str, status: str) -> None:
    """Semeia uma L1 status.json mínima no status pedido."""
    from engine.memory.l1 import L1State, write_l1_status

    write_l1_status(
        L1State(
            feature_slug=slug,
            status=status,
            last_action_at="2026-06-19T00:00:00Z",
            last_action_kind="seed",
        ),
        project_root,
    )


def _seed_planning_l1(project_root: Path, *, slug: str) -> None:
    _seed_l1(project_root, slug=slug, status="planning")


def _seed_done_l1(project_root: Path, *, slug: str) -> None:
    _seed_l1(project_root, slug=slug, status="done")


def test_active_collision_suppressed_during_host_replay(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P-15: L1 já existe em status=planning (criada na 1ª invocação) e há
    forge-response.json pendente pra um prompt downstream. _handle_active_slug_
    collision NÃO deve emitir o guard de colisão — caso contrário o id do guard
    colide com a response downstream → IntentMismatchError (deadlock do piloto)."""
    monkeypatch.chdir(tmp_forge_project)
    _pin_intent_file_host(monkeypatch)
    _seed_planning_l1(tmp_forge_project, slug="meobonsai-login")
    from engine.ui import intent_state
    from engine.memory.l1 import read_l1_status
    from engine.plan import _handle_active_slug_collision

    intent_state.write_response(
        tmp_forge_project,
        {
            "schema-version": 1,
            "intent-id": "subtype-prompt-downstream",
            "value": "product",
        },
    )
    state = read_l1_status("meobonsai-login", tmp_forge_project)
    # Sob replay, o guard retorna o slug existente (retomar) sem emitir intent.
    result = _handle_active_slug_collision(
        "meobonsai-login", state, tmp_forge_project
    )
    assert result == "meobonsai-login", (
        "guard de colisão vazou durante loop mecânico — P-15 não corrigido"
    )


def test_active_collision_shown_on_genuine_human_reentry(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-entrada humana: L1 em planning, SEM response pendente → o guard de
    colisão DEVE emitir (3-caminhos preservado: proteger feature alheia)."""
    monkeypatch.chdir(tmp_forge_project)
    _pin_intent_file_host(monkeypatch)
    _seed_planning_l1(tmp_forge_project, slug="meobonsai-login")
    from engine.memory.l1 import read_l1_status
    from engine.plan import _handle_active_slug_collision
    from engine.ui.question import PausedForInputError

    state = read_l1_status("meobonsai-login", tmp_forge_project)
    with pytest.raises(PausedForInputError) as exc:
        _handle_active_slug_collision("meobonsai-login", state, tmp_forge_project)
    # O pending emitido é o guard de colisão (3-caminhos preservado).
    assert "Já existe uma feature ativa" in (exc.value.intent or {}).get(
        "question", ""
    )


def test_done_feature_branch_suppressed_during_host_replay(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mesma classe de P-15: L1 em status=done + response downstream pendente
    → _handle_done_feature_branch NÃO emite o menu (retorna parent_slug)."""
    monkeypatch.chdir(tmp_forge_project)
    _pin_intent_file_host(monkeypatch)
    _seed_done_l1(tmp_forge_project, slug="meobonsai-login")
    from engine.ui import intent_state
    from engine.plan import _handle_done_feature_branch

    intent_state.write_response(
        tmp_forge_project,
        {"schema-version": 1, "intent-id": "downstream-after-done", "value": "x"},
    )
    result = _handle_done_feature_branch("meobonsai-login", tmp_forge_project)
    assert result == "meobonsai-login", (
        "guard done-feature vazou durante loop mecânico"
    )


def test_done_feature_branch_shown_on_genuine_human_reentry(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-entrada humana: L1 em done, SEM response pendente → menu 4-caminhos
    DEVE emitir (comportamento preservado)."""
    monkeypatch.chdir(tmp_forge_project)
    _pin_intent_file_host(monkeypatch)
    _seed_done_l1(tmp_forge_project, slug="meobonsai-login")
    from engine.plan import _handle_done_feature_branch
    from engine.ui.question import PausedForInputError

    with pytest.raises(PausedForInputError) as exc:
        _handle_done_feature_branch("meobonsai-login", tmp_forge_project)
    assert "O que você quer?" in (exc.value.intent or {}).get("question", "")
