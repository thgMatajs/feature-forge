"""Resume-from-checkpoint tests for ``engine.reconfigure`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: per-subcommand ``_ReconfigureCheckpoint`` dataclass
following ``_InitCheckpoint`` template (``engine/init.py:100-108``).
Lives in this module — NO import from ``engine.qa.checkpoint``.

reconfigure expoe 40 callsites interativos — a maior superficie entre os
10 modulos. Estrutura: 1 top-level menu (category multi-select) → 13
category handlers, cada um com submenus proprios (cards add/remove/
upgrade/lock/inspect, qa toggle/budgets/auditors/retention, card-local
list/add/remove, paths, conventions, backend, persona, memory, hooks,
inventory, graph, cleanup-bak, external-deps). O save eh estrategico
(menu entry + per-category dispatch), nao per-callsite — daria ~5-7
save sites cobrindo todo o fluxo. O resume cobre o cenario canonico em
que o host pausou no draft-resume confirm e re-invoca com response.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (action=add-new, reuse_path=init-pattern)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import reconfigure
from engine.ui import question


# ── Smoke — dataclass + helpers existem (add-new) ────────────────────────────


def test_reconfigure_checkpoint_dataclass_exists() -> None:
    """_ReconfigureCheckpoint dataclass surface must mirror _InitCheckpoint shape."""
    cp_cls = getattr(reconfigure, "_ReconfigureCheckpoint", None)
    assert cp_cls is not None, (
        "_ReconfigureCheckpoint not declared in engine.reconfigure"
    )
    cp = cp_cls(
        step="step-category-menu",
        at="2026-06-10T00:00:00Z",
        project_root="/tmp/foo",
    )
    assert cp.step == "step-category-menu"
    assert getattr(cp, "intent_id", "<missing>") is None
    assert getattr(cp, "menu_path", "<missing>") == []
    assert getattr(cp, "card_name", "<missing>") is None


def test_reconfigure_save_load_clear_roundtrip(tmp_forge_project: Path) -> None:
    """_save/_load/_clear_reconfigure_checkpoint sao idempotentes per outcome C."""
    save = getattr(reconfigure, "_save_reconfigure_checkpoint", None)
    load = getattr(reconfigure, "_load_reconfigure_checkpoint", None)
    clear = getattr(reconfigure, "_clear_reconfigure_checkpoint", None)
    assert save is not None, "_save_reconfigure_checkpoint missing"
    assert load is not None, "_load_reconfigure_checkpoint missing"
    assert clear is not None, "_clear_reconfigure_checkpoint missing"

    cp = reconfigure._ReconfigureCheckpoint(
        step="step-category:cards",
        at="2026-06-10T00:00:00Z",
        project_root=str(tmp_forge_project),
        intent_id="pqr-555",
        menu_path=["cards", "add"],
        card_name="kmp-android",
    )
    save(cp)
    loaded = load(tmp_forge_project)
    assert isinstance(loaded, dict)
    assert loaded.get("step") == "step-category:cards"
    assert loaded.get("intent-id") == "pqr-555"
    assert loaded.get("menu-path") == ["cards", "add"]
    assert loaded.get("card-name") == "kmp-android"

    clear(tmp_forge_project)
    assert load(tmp_forge_project) is None


# ── Comportamento — resume consome response do draft-confirm, nao re-prompta ─


def _seed_workflow_config(project_root: Path) -> None:
    """reconfigure.run exige workflow-config.yaml — escreve um minimo.

    Inclui draft em disco pra triggar o primeiro prompt do handler
    (``question.confirm`` "Detectei um draft de reconfigure ..."). Esse
    eh o entry-point intent-resume canonico do modulo.
    """
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-reconfigure-resume\n",
        encoding="utf-8",
    )
    # Draft minimal — basta existir pra triggar o "retomar draft?" prompt.
    (cfg_dir / ".reconfigure-draft.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-reconfigure-resume\n"
        "  draft-marker: true\n",
        encoding="utf-8",
    )


def test_resume_from_checkpoint(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cenario canonico de resume — checkpoint do draft-confirm + response.json.

    Sequencia simulada:
      1. Invocacao A pausou no ``question.confirm`` "Detectei um draft
         de reconfigure não aplicado. Retomar?" (gravou pending +
         checkpoint com intent_id da pergunta canonica).
      2. Host escreveu ``forge-response.json`` com mesmo intent_id +
         value=False (descarta draft, prossegue limpo).
      3. Invocacao B (este test): reconfigure.run carrega checkpoint,
         descobre intent_id; ``question.confirm`` consome response,
         retorna False sem raise; run prossegue ate o proximo prompt
         (category-multi-select) que NAO tem response no disco —
         entao re-pausa com intent-id DIFERENTE.
      4. forge-response.json original e deletado (consumido).

    O re-pause com intent-id novo prova que: (a) o draft-confirm
    response foi consumido (nao houve re-prompt do mesmo intent-id) e
    (b) o handler avancou pra category menu.
    """
    _seed_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Stage 1 — calcula o intent-id deterministico do draft-confirm.
    # Argumentos seguem o callsite em engine/reconfigure.py:108.
    # question.confirm internamente vira intent kind="confirm" com
    # options={"s": "sim", "n": "não"} e default mapeado de True.
    # Para reproduzir fielmente, replicamos a chamada via _build_pending.
    # Como confirm() em question.py monta options/default proprios, o
    # caminho deterministico mais seguro eh inspecionar a chamada real:
    # confirm(text, default=True) → intent_id derivado de
    # ("confirm", text, {"y": "sim", "n": "não"}, extra={"default": "y", ...})
    # Conservador: vamos calcular tentando ambas as formas e usar a que
    # bate ao chamar dispatch atual; mas o mais robusto eh deixar
    # confirm() escolher a forma e ler do pending.json apos pausa.

    # Stage 1 alternativo: invocamos run() pra deixar engine ESCREVER o
    # pending.json (capturando o intent-id canonico), depois apagamos
    # pending, escrevemos response, e re-invocamos.
    try:
        rc_a = reconfigure.run([])
    except question.PausedForInputError as exc:
        intent_id = exc.intent.get("intent-id")
        first_kind = exc.intent.get("kind")
        first_question = exc.intent.get("question")
    else:
        pytest.fail(
            f"reconfigure.run did not pause on first prompt — got rc={rc_a}"
        )

    assert intent_id, "engine emitted pending sem intent-id"
    assert first_kind == "confirm", (
        f"primeiro prompt era esperado kind=confirm, veio {first_kind!r} "
        f"(question={first_question!r})"
    )

    # Limpa o pending.json escrito pela primeira invocacao — caller
    # consumiu intent, vai escrever response.
    state_dir = tmp_forge_project / ".claude" / "forge" / "state"
    pending_path = state_dir / "forge-pending.json"
    if pending_path.exists():
        pending_path.unlink()

    # Stage 2 — host escreve response.json + persiste checkpoint da
    # invocacao A (simula que ela tinha salvado).
    response_payload = {
        "schema-version": 1,
        "intent-id": intent_id,
        "value": False,  # descarta draft, prossegue limpo
        "responded-at": "2026-06-10T00:01:00Z",
    }
    (state_dir / "forge-response.json").write_text(
        json.dumps(response_payload), encoding="utf-8"
    )
    cp = reconfigure._ReconfigureCheckpoint(
        step="step-draft-confirm",
        at="2026-06-10T00:00:30Z",
        project_root=str(tmp_forge_project),
        intent_id=intent_id,
    )
    reconfigure._save_reconfigure_checkpoint(cp)

    # Sanity — checkpoint + response no disco antes da invocacao B.
    assert reconfigure._load_reconfigure_checkpoint(tmp_forge_project) is not None
    assert (state_dir / "forge-response.json").exists()

    # Stage 3 — invocacao B. question.confirm consome response (False),
    # handler prossegue ate o prompt seguinte (category-multi-select)
    # que NAO tem response no disco — entao re-pausa com intent-id NOVO.
    advanced_past_draft = False
    try:
        reconfigure.run([])
    except question.PausedForInputError as exc:
        new_intent_id = exc.intent.get("intent-id")
        new_kind = exc.intent.get("kind")
        assert new_intent_id != intent_id, (
            f"reconfigure.run re-pausou no mesmo intent-id ({intent_id}) — "
            "draft-confirm response nao foi consumida"
        )
        # O proximo prompt deve ser ask_multi de categorias.
        assert new_kind == "ask_multi", (
            f"prompt apos draft-confirm era esperado ask_multi, veio {new_kind!r}"
        )
        advanced_past_draft = True
    except SystemExit:
        advanced_past_draft = True

    assert advanced_past_draft, (
        "reconfigure.run nao avancou apos consumir o draft-confirm response"
    )

    # Resume contract: response.json original do draft-confirm foi
    # consumido por _clear_state ao retornar valor matched.
    assert not (state_dir / "forge-response.json").exists(), (
        "response file should be consumed/cleared after successful resume"
    )
