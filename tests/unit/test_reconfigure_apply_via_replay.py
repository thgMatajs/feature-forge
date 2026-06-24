"""Repro + regressão do deadlock apply-confirm × draft-resume (P-18).

Contexto (relatório piloto MeoBonsai 2026-06-19, finding P-18): o R4
(`host_is_replaying`) gateou os guards de NAVEGAÇÃO do reconfigure
(draft-resume), mas não o caminho terminal `apply-confirm`. No loop
canônico AI-first o host responde o apply-confirm e re-invoca argv
idêntico. A re-invocação re-entra no topo de ``reconfigure.run``:

  1. há draft em disco → o draft-resume guard vê a response do
     apply-confirm pendente (intent-id ≠ draft-confirm, não-consumida) →
     ``host_is_replaying=True`` → adota o draft silenciosamente;
  2. o pipeline segue pro category-menu (``ask_multi``) — um intent NOVO
     cuja id ≠ apply-confirm id da response em-voo;
  3. ``read_response`` vê id divergente não-consumido → ``IntentMismatchError``
     (exit 1). O apply-confirm NUNCA consome sua response → mutação não
     aplicada.

Este módulo modela o loop nos mesmos helpers de
``tests/unit/test_engine_reconfigure_resume.py`` (P-15): host pinado em
``intent-file`` + responses plantadas no disco. O repro prova o invariante
alvo da D2: sob replay com response de apply-confirm pendente, o pipeline
ALCANCA o apply-confirm e CONSOME a response (aplica a mutação), sem o
category-menu intervir; re-entrada humana genuína ainda mostra o
draft-resume guard.

Refs:
- docs/superpowers/plans/2026-06-19-pilot-r6-aifirst-blockers.md §Grupo D
- docs/schemas/intent-protocol.md §4.1 (host_is_replaying)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import reconfigure
from engine.ui import question


# ── Helpers (espelham test_engine_reconfigure_resume.py) ─────────────────────


def _pin_intent_file_host(project_root: Path) -> None:
    """Pin host=intent-file + semeia a config ativa com qa.enabled=false.

    A config ativa resolve pro primário ``.claude/forge/forge-config.yaml``
    (active_config_path: primário existe → é ele). Semear ``qa.enabled:
    false`` aqui dá um estado vigente DIVERGENTE do draft (qa.enabled:
    true), pra que o caminho de apply tenha uma mutação real a persistir.
    """
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "host: intent-file\n"
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-reconfigure-apply\n"
        "qa:\n"
        "  enabled: false\n",
        encoding="utf-8",
    )
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()
    from engine.ui import intent_state as _intent_state

    _intent_state._reset_log_cache()


def _seed_apply_pending_draft(project_root: Path) -> None:
    """Planta um draft com qa.enabled=true — mutação pendente vs current.

    O draft difere da config vigente (qa.enabled=false) exatamente no
    toggle de qa.enabled; ``working == current`` é falso, então o pipeline
    chega ao apply-confirm em vez de sair cedo com "nenhuma mudança".
    """
    cfg_dir = project_root / ".claude"
    (cfg_dir / ".reconfigure-draft.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-reconfigure-apply\n"
        "qa:\n"
        "  enabled: true\n",
        encoding="utf-8",
    )


def _apply_confirm_intent_id() -> str:
    """intent-id do apply-confirm — single source of truth (IN-04).

    Delega pro próprio engine (`reconfigure._apply_confirm_intent_id`) em vez de
    re-derivar a assinatura do prompt. Re-derivar acoplaria o teste à grafia
    literal do prompt: se o texto mudasse, o id derivado mudaria e o pareamento
    response↔prompt quebraria silenciosamente sem o teste pegar.
    """
    return reconfigure._apply_confirm_intent_id()


def _draft_confirm_intent_id() -> str:
    """intent-id do draft-resume confirm — espelha o callsite L228."""
    return question.stable_intent_id(
        "confirm",
        "Detectei um draft de reconfigure não aplicado. Retomar?",
        {"s": "sim", "n": "não"},
        extra={"default": "s", "min-selected": None, "validator-hint": None},
    )


def _qa_enabled_on_disk(project_root: Path) -> bool | None:
    """Lê qa.enabled da config ativa no disco (pós-run)."""
    from engine.utils.paths import active_config_path
    from engine.utils.yaml_io import read_yaml

    cfg = read_yaml(active_config_path(project_root)) or {}
    qa = cfg.get("qa") or {}
    return qa.get("enabled")


# ── Repro do deadlock (RED) ──────────────────────────────────────────────────


def test_apply_confirm_response_consumed_during_replay(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariante D2: sob replay com response de apply-confirm pendente, o
    pipeline ALCANCA o apply-confirm, consome a response e aplica a mutação
    (qa.enabled → true) — sem o category-menu colidir.

    Antes do fix (RED): o draft-resume guard adota o draft sob replay, segue
    pro category-menu (intent ≠ apply-confirm), e ``read_response`` levanta
    ``IntentMismatchError`` citando o id do category-menu — mutação NÃO
    aplicada (qa.enabled segue false).
    """
    _pin_intent_file_host(tmp_forge_project)
    _seed_apply_pending_draft(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    from engine.ui import intent_state
    from engine.ui.intent_state import IntentMismatchError

    # Estado pré-condição: qa desabilitado na config vigente.
    assert _qa_enabled_on_disk(tmp_forge_project) is False

    # Host respondeu o apply-confirm ("sim, aplicar") e re-invocou argv.
    intent_state.write_response(
        tmp_forge_project,
        {
            "schema-version": 1,
            "intent-id": _apply_confirm_intent_id(),
            "value": True,
        },
    )

    # O pipeline deve alcançar e consumir o apply-confirm sem mismatch.
    try:
        rc = reconfigure.run([])
    except IntentMismatchError as exc:
        pytest.fail(
            "deadlock P-18 reproduzido: o apply-confirm nunca consumiu sua "
            f"response — mismatch no meio do caminho: {exc}"
        )

    # Mutação aplicada: a config no disco reflete qa.enabled=true.
    assert _qa_enabled_on_disk(tmp_forge_project) is True, (
        "apply via replay não persistiu a mutação (qa.enabled segue false)"
    )
    assert rc == 0, f"reconfigure.run devia sair limpo após aplicar, veio rc={rc}"


def test_human_reentry_still_shows_draft_resume(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-entrada humana genuína: draft existe, SEM response in-flight → o
    draft-resume guard DEVE aparecer (invariante humano preservado).

    Trava o lado humano: o fix da D2 não pode suprimir o guard quando não
    há replay em curso.
    """
    _pin_intent_file_host(tmp_forge_project)
    _seed_apply_pending_draft(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    draft_confirm_id = _draft_confirm_intent_id()

    captured: dict | None = None
    try:
        reconfigure.run([])
    except question.PausedForInputError as exc:
        captured = dict(exc.intent or {})

    assert captured is not None, (
        "reconfigure.run devia pausar no draft-confirm em re-entrada humana"
    )
    assert captured.get("intent-id") == draft_confirm_id, (
        "primeiro pending devia ser o draft-resume confirm em re-entrada humana "
        f"sem response in-flight (veio {captured.get('intent-id')!r})"
    )
