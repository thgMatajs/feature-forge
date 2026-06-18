"""Resume-from-checkpoint tests for ``engine.init`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: init **ja tem** ``_InitCheckpoint`` dataclass
(``engine/init.py:100-108``) — o template canonico do outcome C.
T3a audit action="extend": adiciona campo ``intent_id`` pra
correlacionar com ``forge-response.json`` no protocolo intent.

Cenario de resume cobre o gate "Resume de init pendente?" — quando o
checkpoint anterior existe, init pergunta resume/discard/abort. Esse
ask e o ponto natural pra exercitar intent-resume sem ter que
configurar o pipeline inteiro de init (preset, cards, snapshots, etc.).

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (entry init.py — action=extend)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import init
from engine.ui import question


def test_init_checkpoint_dataclass_has_intent_id() -> None:
    """_InitCheckpoint ganha o campo intent_id (None default) no T3b."""
    cp = init._InitCheckpoint(
        step="step-1-greeting",
        at="2026-06-10T00:00:00Z",
        project_root="/tmp/foo",
    )
    # extend contract: campo novo opcional, default None.
    assert hasattr(cp, "intent_id"), "_InitCheckpoint missing intent_id field"
    assert cp.intent_id is None


def test_init_checkpoint_intent_id_roundtrip(tmp_project_root: Path) -> None:
    """_save/_load_checkpoint preservam intent_id no YAML."""
    cp = init._InitCheckpoint(
        step="step-1-greeting",
        at="2026-06-10T00:00:00Z",
        project_root=str(tmp_project_root),
        intent_id="init-intent-xyz",
    )
    init._save_checkpoint(cp)
    payload = init._load_checkpoint(tmp_project_root)
    assert isinstance(payload, dict)
    assert payload.get("intent-id") == "init-intent-xyz", (
        f"intent-id not roundtripped, got {payload}"
    )


def test_resume_from_checkpoint(
    tmp_project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume-resume gate: checkpoint anterior + response 'abort' no disco
    → init pergunta resume?, consome response, retorna 2 (abort path).

    Cenario:
      1. Invocacao A pausou em algum step intermediario (gravou
         checkpoint em .claude/.init-checkpoint.yaml).
      2. Host re-invocou; init detecta checkpoint, pergunta
         'Resume de init pendente?' (intent emitido).
      3. Host escreve response='abort' na forge-response.json.
      4. Re-invocacao consome a response, exibe mensagem 'Ok,
         abortado', retorna 2.
    """
    monkeypatch.chdir(tmp_project_root)

    # Task 0.7b — pin host: intent-file so question.ask delegate writes/reads
    # against .claude/forge/state/ (v1.3 sub-namespace), not stdout.
    forge_dir = tmp_project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "host: intent-file\n", encoding="utf-8"
    )
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()

    # Pre-grava checkpoint simulando pause anterior.
    init._save_checkpoint(
        init._InitCheckpoint(
            step="step-2-discovery",
            at="2026-06-10T00:00:00Z",
            project_root=str(tmp_project_root),
            intent_id=None,  # pause veio do KeyboardInterrupt antigo, sem intent-id
        )
    )

    # Pre-computa intent-id da ask "Resume de init pendente?".
    resume_options = {
        "resume": "começar do zero mantendo o checkpoint como audit",
        "discard": "apagar o checkpoint e começar limpo",
        "abort": "sair sem mexer em nada",
    }
    intent_id = question._stable_intent_id(
        "ask",
        "Resume de init pendente?",
        resume_options,
        extra={
            "default": "discard",
            "min-selected": None,
            "validator-hint": None,
        },
    )

    # Host escreveu response='abort'.
    state_dir = tmp_project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "forge-response.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "intent-id": intent_id,
                "value": "abort",
                "responded-at": "2026-06-10T00:01:00Z",
            }
        ),
        encoding="utf-8",
    )

    # Invoca init.run([]) — chega no gate resume, consome response,
    # retorna exit 1 + tag ABORTED (C3 EXIT-2-COLLISION: o abort NÃO é pausa;
    # exit 2 ficou reservado pra pausa, abort colapsou em 1 + [FORGE-ERR:ABORTED]).
    rc = init.run([])

    assert rc == 1, f"expected abort exit 1, got {rc}"

    # Task 0.7b — CR-002 invariant: state files MUST remain on disk
    # after happy-path consume. cli.py finally block performs the
    # terminal cleanup at handler exit, preserving forensic inspection.
    # Checkpoint preservado (user escolheu abort explicitamente,
    # comportamento existente pre-T3b).
    assert (state_dir / "forge-response.json").exists(), (
        "response file must survive happy-path consume (CR-002)"
    )
    # Checkpoint mantido por contract de init (abort = nao apaga).
    assert init._load_checkpoint(tmp_project_root) is not None, (
        "checkpoint should remain when user picks 'abort'"
    )
