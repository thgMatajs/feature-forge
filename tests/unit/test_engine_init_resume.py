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
    capsys: pytest.CaptureFixture,
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
    # WR-01: trava a CATEGORIA do erro via tag — ==1 sozinho passaria pra
    # qualquer falha; a tag prova que é o caminho de abort explícito.
    captured = capsys.readouterr()
    assert "[FORGE-ERR:ABORTED]" in captured.err, (
        f"esperado tag ABORTED no stderr, obtido: {captured.err!r}"
    )

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


# ── Pilot R1 helpers (P-01 / P-11) ──────────────────────────────────────────


def _pin_intent_file_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Força host=intent-file via escape-hatch env (NÃO escreve config).

    Escrever ``.claude/forge/forge-config.yaml`` dispararia o gate
    INIT-BROWNFIELD ('config já existe') ANTES do bloco de resume — então
    pinamos pelo env ``FORGE_FORCE_INTENT_MODE`` (detect_host §2), que não
    cria o config-path checado pelo gate.
    """
    monkeypatch.setenv("FORGE_FORCE_INTENT_MODE", "1")
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()


def _seed_init_checkpoint(
    project_root: Path, *, step: str, preset: str | None = None
) -> None:
    init._save_checkpoint(
        init._InitCheckpoint(
            step=step,
            at="2026-06-19T00:00:00Z",
            project_root=str(project_root),
            preset=preset,
            intent_id=None,
        )
    )


def _current_resume_labels() -> dict[str, str]:
    """Labels do resume conforme o init atual.

    Pós WS-A-2 existe ``init._resume_option_labels``; antes (WS-A-1) o init
    usa o literal histórico. O helper acompanha o que o init de fato emite.
    """
    fn = getattr(init, "_resume_option_labels", None)
    if callable(fn):
        return fn()
    return {
        "resume": "começar do zero mantendo o checkpoint como audit",
        "discard": "apagar o checkpoint e começar limpo",
        "abort": "sair sem mexer em nada",
    }


def _resume_intent_id(project_root: Path) -> str:
    """intent-id da ask de resume — acompanha as labels que o init emite."""
    return question.stable_intent_id(
        "ask",
        "Resume de init pendente?",
        _current_resume_labels(),
        extra={
            "default": "discard",
            "min-selected": None,
            "validator-hint": None,
        },
    )


def _seed_pending_response(
    project_root: Path, *, intent_id: str, value: str
) -> None:
    state_dir = project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "forge-response.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "intent-id": intent_id,
                "value": value,
                "responded-at": "2026-06-19T00:01:00Z",
            }
        ),
        encoding="utf-8",
    )


_MISMATCH_SENTINEL = {"intent-id": "__downstream-mismatch__"}


def _capture_first_pending(project_root: Path) -> dict | None:
    """Roda init.run([]) e devolve o intent do primeiro pending emitido.

    Sob host=intent-file, a primeira pausa levanta ``PausedForInputError``
    cujo ``.intent`` carrega o payload (com ``intent-id``). Se o init
    consumir a response sem pausar, pode retornar normalmente → None.

    ``IntentMismatchError`` significa que a response no disco não casou com
    o próximo intent do pipeline — mas NÃO é o resume (um leak de resume
    seria CONSUMIDO como resume, não geraria mismatch). Devolvemos um
    sentinel cujo intent-id nunca é o resume_id, provando ausência de leak.
    """
    from engine.ui.question import PausedForInputError
    from engine.ui.intent_state import IntentMismatchError

    try:
        init.run([])
    except PausedForInputError as exc:
        return dict(exc.intent or {})
    except IntentMismatchError:
        return dict(_MISMATCH_SENTINEL)
    return None


def test_resume_prompt_suppressed_when_response_pending(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Loop mecânico do host: existe forge-response.json pendente (pra a
    pergunta real do pipeline, NÃO pro resume) → o init NÃO deve emitir o
    prompt 'Resume de init pendente?'. Caso contrário o intent-id do resume
    colide com a response → IntentMismatchError (P-01 deadlock)."""
    monkeypatch.chdir(tmp_project_root)
    _pin_intent_file_host(monkeypatch)
    _seed_init_checkpoint(tmp_project_root, step="step-5-backend-selection")
    # Loop mecânico do host: existe response pendente pra uma pergunta
    # downstream (não pro resume). Com o gate de P-01, o resume é suprimido —
    # então o pending emitido (se houver) NUNCA é o resume_id. Sem o gate, o
    # resume era emitido e a response orfã colidia → IntentMismatchError.
    _seed_pending_response(
        tmp_project_root, intent_id="qualquer-intent-downstream", value="sim"
    )
    resume_id = _resume_intent_id(tmp_project_root)
    pending = _capture_first_pending(tmp_project_root)
    assert pending is None or pending.get("intent-id") != resume_id, (
        "resume prompt vazou durante loop mecânico — P-01 não corrigido"
    )


def test_resume_prompt_shown_on_genuine_human_reentry(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-entrada humana: checkpoint existe mas NÃO há forge-response.json
    pendente → o prompt de resume DEVE aparecer (comportamento preservado)."""
    monkeypatch.chdir(tmp_project_root)
    _pin_intent_file_host(monkeypatch)
    _seed_init_checkpoint(tmp_project_root, step="step-5-backend-selection")
    resume_id = _resume_intent_id(tmp_project_root)
    pending = _capture_first_pending(tmp_project_root)
    assert pending is not None and pending.get("intent-id") == resume_id, (
        "resume prompt deve aparecer em re-entrada humana sem response pendente"
    )


# ── WS-A-2: resume real (P-11) ──────────────────────────────────────────────


def test_resume_continues_from_checkpoint_step(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resume escolhido em re-entrada humana com checkpoint em
    step-5-backend-selection (preset já confirmado) → o init NÃO deve
    re-perguntar 'Confirmar preset kmp-mobile?'; deve reaproveitar
    checkpoint.preset e seguir do backend selection (P-11).

    Cenário: re-entrada HUMANA (sem response pendente) com checkpoint
    além do preset; a primeira pausa é o resume. Após o host escrever
    'resume', a PRÓXIMA pausa deve ser o backend — nunca o preset.
    """
    monkeypatch.chdir(tmp_project_root)
    _pin_intent_file_host(monkeypatch)
    _seed_init_checkpoint(
        tmp_project_root, step="step-5-backend-selection", preset="kmp-mobile"
    )
    from engine.ui.question import PausedForInputError

    # Iteração 1: re-entrada humana → pausa no resume.
    with pytest.raises(PausedForInputError) as exc1:
        init.run([])
    intent1 = dict(exc1.value.intent or {})
    assert "Resume de init pendente" in intent1.get("question", "")

    # Host escreve 'resume' pra ESSE intent + re-invoca. O gate de P-01
    # suprime o re-prompt do resume; o pipeline continua do step salvo
    # (preset pulado) e pausa no backend. O resume real (WS-A-2) garante
    # que NÃO é o preset.
    _seed_pending_response(
        tmp_project_root, intent_id=intent1.get("intent-id"), value="resume"
    )
    next_pending = _capture_first_pending(tmp_project_root)
    next_q = (next_pending or {}).get("question", "")
    assert "Confirmar preset" not in next_q, (
        f"resume re-perguntou o preset — não continuou do step (P-11): {next_q!r}"
    )


def test_resume_labels_do_not_claim_false_continuation() -> None:
    """Guard de voz: a label da opção que continua não deve afirmar
    'mantendo o checkpoint como audit'. Pós fix, 'resume' = 'continuar'."""
    labels = init._resume_option_labels()
    assert "continuar" in labels["resume"].lower()
    assert "audit" not in labels["resume"].lower()
