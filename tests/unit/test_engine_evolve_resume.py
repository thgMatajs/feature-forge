"""Resume-from-checkpoint tests for ``engine.evolve`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: evolve **ja tem** checkpoint dict-based
(``_write_checkpoint`` / ``_read_checkpoint`` / ``_clear_checkpoint``
em ``engine/evolve.py:55-87``), com payload diferente do
``_InitCheckpoint``. T3a audit action="extend": preserva schema
existente + adiciona o campo ``intent-id`` pro intent-resume.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (entry evolve.py — action=extend)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine import evolve
from engine.ui import question


def _seed_workflow_config(project_root: Path) -> None:
    (project_root / ".claude").mkdir(exist_ok=True)
    (project_root / ".claude" / "workflow-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-slug: evolve-resume\n",
        encoding="utf-8",
    )


def test_evolve_checkpoint_schema_has_intent_id_field(tmp_forge_project: Path) -> None:
    """Apos T3b, _write_checkpoint inclui o campo intent-id (None default)
    no payload gravado.
    """
    _seed_workflow_config(tmp_forge_project)
    evolve._write_checkpoint(
        tmp_forge_project,
        status="deferred-user-pause",
        remaining_ids=["P-001", "P-002"],
        note="test",
    )
    payload = evolve._read_checkpoint(tmp_forge_project)
    assert isinstance(payload, dict)
    # extend contract: schema-version + status + saved-at + remaining
    # ids + note + intent-id (novo). Nao removemos nenhum campo legacy.
    assert payload.get("schema-version") == 1
    assert payload.get("status") == "deferred-user-pause"
    assert payload.get("remaining-proposal-ids") == ["P-001", "P-002"]
    assert "intent-id" in payload, "extend exige campo intent-id no payload"
    assert payload["intent-id"] is None  # default quando nao especificado


def test_evolve_checkpoint_accepts_explicit_intent_id(tmp_forge_project: Path) -> None:
    """_write_checkpoint aceita intent_id kwarg quando o pause vem do prompt."""
    _seed_workflow_config(tmp_forge_project)
    evolve._write_checkpoint(
        tmp_forge_project,
        status="deferred-user-pause",
        remaining_ids=["P-001"],
        note="paused mid-action",
        intent_id="evolve-intent-abc",
    )
    payload = evolve._read_checkpoint(tmp_forge_project)
    assert payload is not None
    assert payload.get("intent-id") == "evolve-intent-abc"


def _queue_proposals(project_root: Path, ids: list[str]) -> None:
    """Escreve a queue minima de propostas em ``.claude/proposed-evolutions.yaml``
    no formato esperado por ``engine.memory.distiller._proposal_from_payload``.
    """
    (project_root / ".claude").mkdir(exist_ok=True)
    proposals = []
    for pid in ids:
        proposals.append(
            {
                "id": pid,
                "type": "promote-to-l2",  # _VALID_KINDS entry
                "confidence": 0.9,
                "created-at": "2026-06-10T00:00:00Z",
                "source": {"features": ["feature-x"], "trigger": "distillation"},
                "rationale": f"Description {pid}",
                "proposed-change": {
                    "target-file": ".claude/memory/L2-project.yaml",
                    "operation": "append",
                    "payload": {"name": pid},
                },
                "provenance": {"count": 1, "feature-slugs": ["feature-x"]},
                "fingerprint": f"fp-{pid}",
            }
        )
    import yaml

    (project_root / ".claude" / "proposed-evolutions.yaml").write_text(
        yaml.safe_dump(
            {
                "schema-version": 1,
                "last-updated": "2026-06-10T00:00:00Z",
                "last-source": "memory-distiller",
                "proposals": proposals,
            }
        ),
        encoding="utf-8",
    )


def test_resume_from_checkpoint(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume canonico evolve — checkpoint + response.json corresponde ao
    action ask, fluxo consome e termina o loop.

    Cenario com UMA proposta pra resume clean ate o fim (sem segundo
    prompt). Sequencia:
      1. Invocacao A pausou em _action_for(P-001) — gravou checkpoint
         com remaining-proposal-ids=["P-001"] + intent_id da pergunta.
      2. Host escreveu forge-response.json escolhendo "d" (depois) pra
         P-001 — proposta fica pendente, cursor avanca, loop termina.
      3. Invocacao B (este test): evolve carrega checkpoint, filtra a
         queue, _action_for(P-001) consome response.json, retorna "d",
         loop termina, checkpoint apagado.
    """
    _seed_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Task 0.7b — pin host: intent-file so question.ask delegate writes/reads
    # against .claude/forge/state/ (v1.3 sub-namespace), not stdout.
    forge_dir = tmp_forge_project / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "host: intent-file\n", encoding="utf-8"
    )
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()

    _queue_proposals(tmp_forge_project, ["P-001"])

    # Pre-computa intent-id da action ask do P-001 (espelha _action_for):
    intent_id_p001 = evolve._action_intent_id("P-001")

    # Escreve response + checkpoint (action: "d" defer pra P-001).
    state_dir = tmp_forge_project / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "forge-response.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "intent-id": intent_id_p001,
                "value": "d",
                "responded-at": "2026-06-10T00:01:00Z",
            }
        ),
        encoding="utf-8",
    )
    evolve._write_checkpoint(
        tmp_forge_project,
        status="awaiting-action-response",
        remaining_ids=["P-001"],
        note="resumo via test",
        intent_id=intent_id_p001,
    )
    assert evolve._read_checkpoint(tmp_forge_project) is not None

    rc = evolve.run([])

    # Loop consumiu response do P-001, escolheu "d" (defer), cursor
    # avancou (proposta nao removida da queue — "d" so move o cursor),
    # loop terminou clean.
    assert rc == 0, f"unexpected exit code from evolve.run: {rc}"

    # Task 0.7b — CR-002 invariant: state files MUST remain on disk
    # after happy-path consume. cli.py finally block performs the
    # terminal cleanup at handler exit, preserving forensic inspection.
    assert (state_dir / "forge-response.json").exists(), (
        "response file must survive happy-path consume (CR-002)"
    )

    # Checkpoint apagado apos clean completion (linha _clear_checkpoint
    # ao final de evolve.run quando loop termina).
    assert evolve._read_checkpoint(tmp_forge_project) is None, (
        "checkpoint should be cleared on clean completion"
    )


# ── Task 2 (6b / D5): overflow-skip pra kinds de conhecimento ─────────────


def test_apply_proposal_skips_overflow_for_knowledge_kind(tmp_path, monkeypatch):
    """Knowledge proposal NÃO é bloqueado por L2-overflow (D5).

    detect_l2_overflow é forçado a True; mem_inbox_add (via route_proposal_to_inbox)
    é stubado pra sucesso. O proposal de conhecimento deve aplicar (retorna True),
    provando que o guard foi pulado.
    """
    import engine.evolve as _evolve
    from engine.memory.distiller import DistillationProposal

    # Força overflow True — se o guard NÃO fosse pulado, _apply_proposal retornaria False.
    monkeypatch.setattr(_evolve, "detect_l2_overflow", lambda root, cfg: True)
    # Stuba o apply pra não tocar mem real nem L2.
    applied: list = []
    monkeypatch.setattr(
        _evolve, "route_proposal_to_inbox",
        lambda root, p: applied.append(p.id),
    )

    p = DistillationProposal(
        id="P-know",
        kind="promote-to-l2",
        title="t",
        description="d",
        provenance=["auth"],
        confidence=0.7,
    )
    # W-ROUTE 6d: _apply_proposal agora retorna (success, inbox_id).
    success, _inbox_id = _evolve._apply_proposal(tmp_path, p, {})
    assert success is True, "knowledge proposal foi bloqueado pelo overflow-guard (D5 falhou)"
    assert applied == ["P-know"]


def test_apply_proposal_keeps_overflow_guard_for_non_knowledge_kind(tmp_path, monkeypatch):
    """forget-l1 (não-conhecimento) AINDA respeita o overflow-guard (regression)."""
    import engine.evolve as _evolve
    from engine.memory.distiller import DistillationProposal

    monkeypatch.setattr(_evolve, "detect_l2_overflow", lambda root, cfg: True)
    applied: list = []
    monkeypatch.setattr(
        _evolve, "route_proposal_to_inbox",
        lambda root, p: applied.append(p.id),
    )

    p = DistillationProposal(
        id="P-forget",
        kind="forget-l1",
        title="t",
        description="d",
        provenance=["auth"],
        payload={"target": "auth"},
    )
    # W-ROUTE 6d: pausa por overflow retorna (False, None).
    success, inbox_id = _evolve._apply_proposal(tmp_path, p, {})
    assert success is False, "forget-l1 deveria ser pausado por overflow (guard preservado)"
    assert inbox_id is None, "pausa por overflow não carrega inbox-id"
    assert applied == [], "apply não deveria rodar sob overflow para kind não-conhecimento"


# ── Task 2 (6d): _apply_proposal propaga o mem-inbox-id ───────────────────────


def test_evolve_apply_records_mem_inbox_id(tmp_path, monkeypatch):
    """W-ROUTE 6d: aplicar um knowledge proposal devolve o inbox-id na tupla."""
    import engine.evolve as _evolve
    from engine.memory.distiller import DistillationProposal

    monkeypatch.setattr(_evolve, "route_proposal_to_inbox", lambda root, p: "01INBOXID")
    monkeypatch.setattr(_evolve, "detect_l2_overflow", lambda root, cfg: False)

    p = DistillationProposal(
        id="P-know",
        kind="promote-to-l2",
        title="t",
        description="d",
        provenance=["auth"],
        confidence=0.7,
    )
    ok, inbox_id = _evolve._apply_proposal(tmp_path, p, cfg={})
    assert ok is True
    assert inbox_id == "01INBOXID"


# ── P4 (cross-AI PR#32): preflight overflow só quando há proposta que toca L2 ──


def test_preflight_overflow_skipped_when_queue_is_all_knowledge(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P4: fila só-knowledge + L2 legada cheia → o preflight NÃO bloqueia.

    `detect_l2_overflow` é forçado a True. Se o preflight ainda rodasse sobre a
    fila inteira, `run()` abriria o gate de 3-caminhos e nunca processaria os
    knowledge kinds (que só roteiam pro mem-inbox). Com o fix, o preflight é
    pulado e o loop aplica normalmente.
    """
    from engine.memory.distiller import DistillationProposal

    _seed_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)
    forge_dir = tmp_forge_project / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text("host: intent-file\n", encoding="utf-8")
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()

    monkeypatch.setattr(evolve, "detect_l2_overflow", lambda root, cfg: True)

    knowledge = [
        DistillationProposal(
            id="P-k1", kind="promote-to-l2", title="t1", description="d1",
            provenance=["auth"], confidence=0.7, fingerprint="",
        ),
        DistillationProposal(
            id="P-k2", kind="consolidate-l2", title="t2", description="d2",
            provenance=["cart"], confidence=0.6, fingerprint="",
        ),
    ]
    monkeypatch.setattr(
        evolve, "read_proposals_queue", lambda root: list(knowledge)
    )
    monkeypatch.setattr(evolve, "_filter_rejected", lambda root, ps: (list(ps), 0))

    # Se o preflight disparasse, _three_paths_overflow seria chamado — falha o teste.
    def _boom(*a, **k):  # pragma: no cover - só dispara em regressão
        raise AssertionError("preflight overflow disparou para fila só-knowledge (P4)")

    monkeypatch.setattr(evolve, "_three_paths_overflow", _boom)

    applied: list[str] = []

    def _fake_apply(root, p, cfg):
        applied.append(p.id)
        return (True, "01INBOX")

    monkeypatch.setattr(evolve, "_apply_proposal", _fake_apply)
    # Auto-aprovar ("a") cada proposta no loop single-by-single.
    monkeypatch.setattr(evolve, "_action_for", lambda p: "a")

    rc = evolve.run([])
    assert rc == 0
    assert applied == ["P-k1", "P-k2"], "knowledge applies não prosseguiram sob L2 cheia (P4)"


# ── P6 (cross-AI PR#32): _record_history_event avisa em vez de swallow ────────


def test_record_history_event_warns_on_append_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """P6: se `append_history` falhar (OSError), emite aviso visível e não propaga.

    O evento `evolve-apply` carrega o `mem-inbox-id` load-bearing pro recovery —
    swallow silencioso orfanaria o candidato. Espelha `undo._append_undo_log`.
    """
    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(evolve, "append_history", _boom)

    # Não deve propagar.
    evolve._record_history_event(
        tmp_path, "evolve-apply", "P-know",
        extras={"routed-to": "mem-inbox", "mem-inbox-id": "01INBOX"},
    )
    out = capsys.readouterr().out
    assert "evento evolve" in out, "P6: append-fail deveria emitir aviso visível"


def test_record_history_event_does_not_swallow_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P6: o narrow do except NÃO mascara bugs reais — uma exceção fora de
    (OSError, ValueError) propaga em vez de virar swallow silencioso."""
    def _boom(*a, **k):
        raise RuntimeError("bug de serialização inesperado")

    monkeypatch.setattr(evolve, "append_history", _boom)

    with pytest.raises(RuntimeError):
        evolve._record_history_event(tmp_path, "evolve-apply", "P-x")
