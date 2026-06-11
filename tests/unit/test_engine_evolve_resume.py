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

    _queue_proposals(tmp_forge_project, ["P-001"])

    # Pre-computa intent-id da action ask do P-001 (espelha _action_for):
    intent_id_p001 = evolve._action_intent_id("P-001")

    # Escreve response + checkpoint (action: "d" defer pra P-001).
    state_dir = tmp_forge_project / ".claude" / "state"
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

    # Response consumida pelo question.ask.
    assert not (state_dir / "forge-response.json").exists(), (
        "response should be consumed/cleared on resume"
    )

    # Checkpoint apagado apos clean completion (linha _clear_checkpoint
    # ao final de evolve.run quando loop termina).
    assert evolve._read_checkpoint(tmp_forge_project) is None, (
        "checkpoint should be cleared on clean completion"
    )
