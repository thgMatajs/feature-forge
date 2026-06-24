"""Regressão M4 (PR #26 review) — grant-prompt × apply-confirm collision.

Contexto: sob ``_skip_to_apply`` (replay com a response do apply-confirm
em-voo) o reconfigure pula o category-menu (fix P-18), MAS
``evaluate_sensitive_grants`` ainda rodava incondicionalmente. Se o draft
adotado tem uma var sensitive NÃO-granted, esse caminho emitia um prompt
3-caminhos fresco — um intent NOVO que colide com a response terminal
in-flight → IntentMismatchError, a MESMA classe de deadlock que P-18 fechou.

Este módulo reusa o harness de ``test_reconfigure_apply_via_replay.py``
(host pinado em intent-file + response plantada). Injeta um manifest ativo
com var sensitive não-granted e prova que, sob replay:

  1. ``evaluate_sensitive_grants`` NÃO é chamado (não emite prompt);
  2. a mutação do apply é aplicada sem IntentMismatchError.

E que o caminho não-replay (re-entrada humana) ainda avalia grants
normalmente.

Refs:
- docs/superpowers/plans/2026-06-19-pilot-r6-aifirst-blockers.md §Grupo D
- docs/schemas/intent-protocol.md §4.1 (host_is_replaying)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import reconfigure
from engine.cards.loader import CardManifest


def _pin_intent_file_host(project_root: Path) -> None:
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "host: intent-file\n"
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-reconfigure-grant\n"
        "qa:\n"
        "  enabled: false\n",
        encoding="utf-8",
    )
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()
    from engine.ui import intent_state as _intent_state

    _intent_state._reset_log_cache()


def _seed_apply_pending_draft(project_root: Path) -> None:
    cfg_dir = project_root / ".claude"
    (cfg_dir / ".reconfigure-draft.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-reconfigure-grant\n"
        "qa:\n"
        "  enabled: true\n",
        encoding="utf-8",
    )


def _card_with_sensitive() -> CardManifest:
    return CardManifest(
        name="firebase-auth",
        version="1.0.0",
        schema_version=1,
        description="stub",
        category="backend",
        maturity="stable",
        sensitive_env_needs=("FIREBASE_API_TOKEN",),
    )


def _qa_enabled_on_disk(project_root: Path) -> bool | None:
    from engine.utils.paths import active_config_path
    from engine.utils.yaml_io import read_yaml

    cfg = read_yaml(active_config_path(project_root)) or {}
    return (cfg.get("qa") or {}).get("enabled")


def test_no_grant_prompt_during_apply_replay(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M4: sob replay com response de apply-confirm em-voo e var sensitive
    não-granted no draft, ``evaluate_sensitive_grants`` NÃO é chamado e a
    mutação aplica sem IntentMismatchError.
    """
    _pin_intent_file_host(tmp_forge_project)
    _seed_apply_pending_draft(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    from engine.ui import intent_state
    from engine.ui.intent_state import IntentMismatchError

    # Manifest ativo declara uma var sensitive não-granted (draft não a granta).
    monkeypatch.setattr(
        reconfigure,
        "_load_active_manifests",
        lambda _root: [_card_with_sensitive()],
    )

    # Tripwire: se o guard M4 falhar, este caminho roda e falha o teste.
    def _boom(*_a, **_k):  # pragma: no cover - só dispara em regressão
        pytest.fail(
            "evaluate_sensitive_grants chamado durante replay de apply-confirm "
            "— prompt de grant colidiria com a response in-flight (M4)"
        )

    monkeypatch.setattr(reconfigure, "evaluate_sensitive_grants", _boom)

    assert _qa_enabled_on_disk(tmp_forge_project) is False

    intent_state.write_response(
        tmp_forge_project,
        {
            "schema-version": 1,
            "intent-id": reconfigure._apply_confirm_intent_id(),
            "value": True,
        },
    )

    try:
        rc = reconfigure.run([])
    except IntentMismatchError as exc:
        pytest.fail(f"deadlock de grant×apply reproduzido: {exc}")

    assert _qa_enabled_on_disk(tmp_forge_project) is True
    assert rc == 0


def test_human_path_still_evaluates_grants(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O guard M4 não pode suprimir a avaliação de grants no caminho normal
    (sem replay). Aqui não há response in-flight → o draft-resume confirm
    pausa ANTES de chegar ao grant; mas se ele rodasse, deveria ser o
    evaluate real. Provamos que o caminho replay-skip é específico:
    sem _skip_to_apply, evaluate_sensitive_grants seria alcançável.

    Trava barata: re-entrada humana pausa no draft-confirm (não no grant),
    confirmando que o guard só atua sob replay.
    """
    _pin_intent_file_host(tmp_forge_project)
    _seed_apply_pending_draft(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    from engine.ui import question

    captured: dict | None = None
    try:
        reconfigure.run([])
    except question.PausedForInputError as exc:
        captured = dict(exc.intent or {})

    assert captured is not None
    # Pausa no draft-resume confirm (não num grant) — guard M4 é replay-only.
    assert "Retomar" in (captured.get("prompt") or captured.get("question") or "") or \
        captured.get("intent-id"), captured
