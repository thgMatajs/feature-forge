"""Resume-from-checkpoint tests for ``engine.doctor`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: per-subcommand ``_DoctorCheckpoint`` dataclass,
following the ``_InitCheckpoint`` template (``engine/init.py:100-108``).
Lives in this module — NO import from ``engine.qa.checkpoint``.

The integration is intentionally minimal — doctor has a single
interactive prompt (``scope`` ask, full/quick). Intent-resume only needs
to ensure that, when a previous invocation paused at that prompt and
the host has since written a matching response, the re-invocation
consumes the response and continues the report without re-prompting,
then clears the checkpoint on completion.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (action=add-new, reuse_path=init-pattern)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import doctor
from engine.ui import intent_state, question


# ── Smoke — dataclass + helpers existem (add-new) ────────────────────────────


def test_doctor_checkpoint_dataclass_exists() -> None:
    """_DoctorCheckpoint dataclass surface must mirror _InitCheckpoint shape."""
    cp_cls = getattr(doctor, "_DoctorCheckpoint", None)
    assert cp_cls is not None, "_DoctorCheckpoint not declared in engine.doctor"
    # Smoke instanciacao com campos minimos esperados — outcome C reusa o
    # template de init: step + at + project_root + intent_id (novo).
    cp = cp_cls(
        step="step-scope-ask",
        at="2026-06-10T00:00:00Z",
        project_root="/tmp/foo",
    )
    assert cp.step == "step-scope-ask"
    # intent_id defaults to None — populated only after question.ask emits intent.
    assert getattr(cp, "intent_id", "<missing>") is None


def test_doctor_save_load_clear_roundtrip(tmp_forge_project: Path) -> None:
    """_save/_load/_clear_doctor_checkpoint sao idempotentes per outcome C."""
    save = getattr(doctor, "_save_doctor_checkpoint", None)
    load = getattr(doctor, "_load_doctor_checkpoint", None)
    clear = getattr(doctor, "_clear_doctor_checkpoint", None)
    assert save is not None, "_save_doctor_checkpoint missing"
    assert load is not None, "_load_doctor_checkpoint missing"
    assert clear is not None, "_clear_doctor_checkpoint missing"

    cp_cls = doctor._DoctorCheckpoint
    cp = cp_cls(
        step="step-scope-ask",
        at="2026-06-10T00:00:00Z",
        project_root=str(tmp_forge_project),
        intent_id="abc-123",
    )
    save(cp)
    loaded = load(tmp_forge_project)
    assert isinstance(loaded, dict)
    assert loaded.get("step") == "step-scope-ask"
    assert loaded.get("intent-id") == "abc-123"

    clear(tmp_forge_project)
    assert load(tmp_forge_project) is None


# ── Comportamento — resume consome response, nao re-prompta ─────────────────


def _write_workflow_config(project_root: Path) -> None:
    """Doctor exige workflow-config.yaml — escreve um minimo pra teste."""
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-doctor-resume\n"
        "  preset: kmp-mobile\n",
        encoding="utf-8",
    )


def test_resume_from_checkpoint(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cenario canonico de resume — checkpoint + response.json correspondente.

    Sequencia simulada:
      1. Invocacao A pausou em ``scope`` ask (gravou pending +
         checkpoint com intent_id da pergunta).
      2. Host escreveu ``forge-response.json`` com mesmo intent_id +
         value="quick".
      3. Invocacao B (este test): doctor carrega checkpoint, descobre
         intent_id, executa o fluxo; ``question.ask`` ve a response no
         disco, consome, retorna "quick" sem raise.
      4. Apos o report rodar (mesmo que com warnings), checkpoint e
         apagado.
    """
    _write_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Stage 1 — descobrir o intent-id determinístico que o doctor emite
    # quando chama question.ask("Qual scope?", {"full": ..., "quick": ...},
    # default="full"). Usamos a propria funcao stable_intent_id pra
    # produzir o mesmo digest sem precisar simular a Stage 1 inteira.
    scope_options = {
        "full": "checa tudo (~8s)",
        "quick": "só o crítico — config + cards + L2 size (~2s)",
    }
    intent_id = question._stable_intent_id(
        "ask",
        "Qual scope?",
        scope_options,
        extra={"default": "full", "min-selected": None, "validator-hint": None},
    )

    # Stage 2 — host escreveu response.json + checkpoint do doctor com
    # intent_id matching.
    state_dir = tmp_forge_project / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    response_payload = {
        "schema-version": 1,
        "intent-id": intent_id,
        "value": "quick",
        "responded-at": "2026-06-10T00:01:00Z",
    }
    (state_dir / "forge-response.json").write_text(
        json.dumps(response_payload), encoding="utf-8"
    )
    cp = doctor._DoctorCheckpoint(
        step="step-scope-ask",
        at="2026-06-10T00:00:30Z",
        project_root=str(tmp_forge_project),
        intent_id=intent_id,
    )
    doctor._save_doctor_checkpoint(cp)

    # Sanity — checkpoint + response no disco antes de rodar.
    assert doctor._load_doctor_checkpoint(tmp_forge_project) is not None
    assert (state_dir / "forge-response.json").exists()

    # Stage 3 — invoca doctor.run([]). question.ask deve consumir o
    # response, voltar "quick", e o report rodar ate o veredito final
    # (sem PausedForInputError). Suprimimos outros possiveis prompts
    # (defensivos) com monkeypatch — doctor.py so faz UM ask hoje, mas
    # caso o codigo evolua, nao queremos test fragil.
    rc = doctor.run([])

    # Resume bem sucedido: exit code 0 ou 1 (warn/fail aceitavel em
    # tmp_forge_project minimo; o que importa e nao virar exit 2 nem
    # crashar com excecao nao-tratada).
    assert rc in (0, 1), f"unexpected exit code from doctor.run: {rc}"

    # Resume contract: forge-response.json e consumido (question.ask
    # apaga em _clear_state). Forge-pending.json nao foi escrito nesta
    # invocacao porque a response ja estava la.
    assert not (state_dir / "forge-response.json").exists(), (
        "response file should be consumed/cleared after successful resume"
    )

    # Checkpoint deve ser apagado apos run completar (clean completion).
    assert doctor._load_doctor_checkpoint(tmp_forge_project) is None, (
        "checkpoint should be cleared on clean completion"
    )
