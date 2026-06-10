"""Integration tests — DRIFT-1 intent protocol end-to-end (W5.T1).

Cobre AC-1, AC-2, AC-6, AC-7 da spec:

- **AC-1** — engine emite ``forge-pending.json`` no primeiro prompt e sai
  com exit 2.
- **AC-2** — re-invocação com ``forge-response.json`` válido consome a
  resposta, limpa o estado e avança (exit 0 OU exit 2 com novo
  intent-id).
- **AC-6** — happy path: ambos arquivos de estado são deletados após
  consumo bem-sucedido. Intent-id mismatch: arquivos preservados
  forensicamente, exit 1.
- **AC-7** — race detection: pending pré-existente recente (≤ 10min) com
  intent-id diferente do que seria escrito → exit 1 + pending intacto.

Estratégia de escolha de subcomando:
  Usamos ``forge undo``. Razão: ele pula direto pra ``question.ask`` do
  menu (linha 581 de ``engine/undo.py``), sem precisar rodar a pipeline
  pesada de discovery do ``init``. ``find_project_root`` exige um
  ``.claude/workflow-config.yaml`` upstream, então cada teste monta um
  tmp_path com ``.claude/workflow-config.yaml`` vazio (``{}``) — config
  válida pelos parsers do projeto, suficiente pra ``undo`` chegar ao
  menu.

Refs:
- ``docs/superpowers/specs/drift-1-intent-protocol.md`` §2-§4, §8, §9
- ``docs/superpowers/plans/drift-1-intent-protocol.md`` W5.T1
- ``engine/ui/question.py`` (chokepoint)
- ``engine/ui/intent_state.py`` (state file I/O)
- ``engine/cli.py`` (exit-code ladder)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# Project root resolves from this file: tests/integration/test_X.py → repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Subcommand chosen for these tests: lightweight, prompts on the first
# line of execution after find_project_root. See module docstring.
SUBCOMMAND = "undo"

# Timeout for each subprocess. Comfortable margin over local hot path
# (~1s) without making a hung process drag CI.
SUBPROCESS_TIMEOUT = 30


# ── Helpers ──────────────────────────────────────────────────────────────────


def _scaffold_project(tmp_path: Path) -> Path:
    """Create the minimal ``.claude/`` layout that ``find_project_root`` needs.

    ``find_project_root`` walks upward looking for
    ``.claude/workflow-config.yaml``. We write an empty mapping (``{}``)
    — the YAML parser accepts it and downstream readers
    (``read_yaml_or_default``) treat it as "no overrides". Enough for
    ``undo`` to reach the menu prompt.
    """
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    (claude / "state").mkdir(exist_ok=True)
    return tmp_path


def _run_engine(
    project_root: Path,
    *,
    subcommand: str = SUBCOMMAND,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke ``python -m engine.cli <subcommand>`` in the tmp project root.

    Strips inherited TTY-related env vars and sets ``stdin=DEVNULL`` so
    the dispatcher's non-TTY detection lights up unambiguously. The
    intent-mode path is the only one we want exercised here.
    """
    env = os.environ.copy()
    # Make sure PYTHONPATH includes the worktree so `python -m engine.cli`
    # resolves even if pytest's path manipulation is per-process.
    pythonpath = str(PROJECT_ROOT)
    env["PYTHONPATH"] = (
        pythonpath + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else pythonpath
    )
    # FORGE_HOME anchors auxiliary lookups (cards/, agents/, etc.) — the
    # canonical worktree owns the engine sources we just imported.
    env["FORGE_HOME"] = str(PROJECT_ROOT)
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [sys.executable, "-m", "engine.cli", subcommand],
        cwd=str(project_root),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
    )


def _pending_path(project_root: Path) -> Path:
    return project_root / ".claude" / "state" / "forge-pending.json"


def _response_path(project_root: Path) -> Path:
    return project_root / ".claude" / "state" / "forge-response.json"


def _read_pending(project_root: Path) -> dict:
    path = _pending_path(project_root)
    assert path.is_file(), f"expected pending at {path}, not found"
    return json.loads(path.read_text(encoding="utf-8"))


def _write_response(project_root: Path, payload: dict) -> None:
    """Atomically-equivalent write — small enough that a single write is fine."""
    path = _response_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── AC-1 — first invocation emits intent + exit 2 ────────────────────────────


def test_init_emits_intent_first_prompt(tmp_path):
    """AC-1 — primeira invocação emite pending JSON e sai com exit 2.

    Schema validado contra ``docs/schemas/intent-protocol.md`` /
    SPEC §2.1: campos canônicos presentes, ``kind`` enumerado, ``options``
    bem-formado (quando aplicável), ``intent-id`` no formato UUID-like.

    O subcomando escolhido (``undo``) usa ``kind="ask"`` no menu — a
    asserção sobre options/kind é específica desse caso; estrutura geral
    do schema funciona pra qualquer kind.
    """
    project_root = _scaffold_project(tmp_path)

    result = _run_engine(project_root)

    assert result.returncode == 2, (
        f"expected exit 2 (paused-for-input), got {result.returncode}; "
        f"stderr={result.stderr!r}; stdout={result.stdout!r}"
    )

    pending = _read_pending(project_root)

    # Schema-version contract (SPEC §2.1).
    assert pending.get("schema-version") == 1, pending

    # intent-id present and UUID-shaped (8-4-4-4-12 hex).
    intent_id = pending.get("intent-id")
    assert isinstance(intent_id, str) and len(intent_id) == 36, intent_id
    parts = intent_id.split("-")
    assert [len(p) for p in parts] == [8, 4, 4, 4, 12], (
        f"intent-id not UUID-shaped: {intent_id!r}"
    )

    # Kind is one of the canonical five.
    assert pending.get("kind") in (
        "ask",
        "ask_text",
        "ask_multi",
        "confirm",
        "ask_three_paths",
    ), pending.get("kind")

    # Question is a non-empty string.
    question = pending.get("question")
    assert isinstance(question, str) and question, question

    # Command echo — should reflect the subcommand we invoked.
    assert pending.get("command") == SUBCOMMAND, pending.get("command")

    # ``allow-pause`` is a bool — required by schema.
    assert isinstance(pending.get("allow-pause"), bool), pending

    # ``created-at`` ISO-8601 UTC.
    created = pending.get("created-at")
    assert isinstance(created, str) and created.endswith("Z"), created

    # ``pid`` is an integer.
    assert isinstance(pending.get("pid"), int) and pending.get("pid") > 0, pending

    # ``options`` exists for kinds that carry it (ask/ask_multi/confirm/
    # ask_three_paths). ``undo`` uses ``ask`` so options must be a dict.
    if pending.get("kind") in ("ask", "ask_multi", "confirm", "ask_three_paths"):
        options = pending.get("options")
        assert isinstance(options, dict) and options, options

    # Response file NOT written by the engine (caller side only).
    assert not _response_path(project_root).exists(), (
        "engine should not write the response file"
    )


# ── AC-2 + AC-6 happy path — response consumed, state cleared ────────────────


def test_resume_consumes_response_and_deletes(tmp_path):
    """AC-2 / AC-6 — escrever response com intent-id correto consome a
    resposta. Após consumo, ambos arquivos de estado são deletados.

    ``undo`` continua dispatching pro branch escolhido após o menu; em
    muitos branches isso leva a outro prompt → exit 2 com novo
    intent-id. Aceitamos exit 0 OU exit 2-com-novo-intent-id — ambos
    significam "estado avançou" (a única regressão seria exit 1 ou exit
    2-com-mesmo-intent-id).
    """
    project_root = _scaffold_project(tmp_path)

    # First invocation → pause.
    first = _run_engine(project_root)
    assert first.returncode == 2, first.stderr
    first_pending = _read_pending(project_root)
    first_intent_id = first_pending["intent-id"]

    # Reply with "c" (cancel) — ``undo`` recognises it and exits 0 cleanly,
    # which is the simplest deterministic continuation.
    _write_response(
        project_root,
        {
            "schema-version": 1,
            "intent-id": first_intent_id,
            "kind": first_pending["kind"],
            "value": "c",
            "answered-at": _iso_now(),
        },
    )

    # Second invocation → consume + advance.
    second = _run_engine(project_root)

    # Exit code allowed values:
    #   0  → ``undo`` finished cleanly after cancel.
    #   2  → engine advanced to a follow-up prompt (acceptable per AC-2).
    # exit 1 here would mean intent-id mismatch or schema problem — a
    # regression.
    assert second.returncode in (0, 2), (
        f"unexpected exit {second.returncode}; stderr={second.stderr!r}; "
        f"stdout={second.stdout!r}"
    )

    if second.returncode == 0:
        # Happy clean completion — both state files MUST be gone (AC-6).
        assert not _pending_path(project_root).exists(), (
            "pending file should be deleted on clean completion"
        )
        assert not _response_path(project_root).exists(), (
            "response file should be deleted on clean completion"
        )
    else:
        # Engine advanced — old response is consumed regardless. New
        # pending exists with a DIFFERENT intent-id (state moved
        # forward). The old response file MUST be gone (AC-6 still
        # applies for the consumed payload).
        assert not _response_path(project_root).exists(), (
            "response file should be deleted after successful consume"
        )
        new_pending = _read_pending(project_root)
        assert new_pending["intent-id"] != first_intent_id, (
            "engine did not advance — same intent-id re-emitted"
        )


# ── AC-7 — race detection ────────────────────────────────────────────────────


def test_race_detection_rejects_stale_concurrent(tmp_path):
    """AC-7 — pending pré-existente recente com intent-id diferente do
    que a engine ia escrever → exit 1 + pending preservado.

    Pre-staging um pending sintético com timestamp recente (10s atrás).
    A engine vê o conflito antes de chamar ``write_pending``, levanta
    ``RaceDetectedError``, e ``cli.main`` mapeia pra exit 1 com a
    mensagem mentor-calmo carried in args[0].
    """
    project_root = _scaffold_project(tmp_path)

    # Stage a recent pending with a clearly-different intent-id.
    stale_id = str(uuid.uuid4())
    recent = datetime.now(timezone.utc) - timedelta(seconds=10)
    pre_existing = {
        "schema-version": 1,
        "intent-id": stale_id,
        "command": "init",  # unrelated subcommand
        "command-args": [],
        "kind": "ask",
        "question": "Pre-staged race probe",
        "options": {"a": "alpha", "b": "beta"},
        "default": None,
        "allow-pause": True,
        "created-at": recent.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pid": 99999,
        "checkpoint-path": None,
    }
    _pending_path(project_root).write_text(
        json.dumps(pre_existing), encoding="utf-8"
    )

    # Run the engine — must detect the race before writing its own pending.
    result = _run_engine(project_root)

    assert result.returncode == 1, (
        f"expected exit 1 on race, got {result.returncode}; "
        f"stderr={result.stderr!r}; stdout={result.stdout!r}"
    )

    # The pre-existing pending MUST remain intact (forensic preservation
    # per SPEC §9; engine never overwrites a recent concurrent pending).
    assert _pending_path(project_root).is_file(), (
        "race detection should NOT delete the pre-existing pending"
    )
    preserved = json.loads(
        _pending_path(project_root).read_text(encoding="utf-8")
    )
    assert preserved["intent-id"] == stale_id, (
        "pre-existing pending intent-id was tampered with"
    )


# ── AC-6 negative — intent-id mismatch preserves both files ──────────────────


def test_response_intent_id_mismatch_exits_error(tmp_path):
    """AC-6 negative — response com intent-id que não bate com o pending
    em disco → exit 1 e AMBOS arquivos preservados (forensic, SPEC §3).

    Sequência:
      1. Primeira invocação emite pending(id=A) + exit 2.
      2. Escrevemos response com intent-id=B (≠ A).
      3. Re-invocação: ``read_response`` levanta ``IntentMismatchError``;
         como pending(id=A) ainda está no disco, race detection se
         resolve via "mesmo intent-id" — engine re-emite pending(id=A) e
         encontra o response(id=B), levanta mismatch.
      4. ``cli.main`` mapeia exception não-listada pra exit 1.
      5. Nenhum dos arquivos é apagado (preservação forense).
    """
    project_root = _scaffold_project(tmp_path)

    # First invocation → pause + pending(id=A).
    first = _run_engine(project_root)
    assert first.returncode == 2, first.stderr
    first_pending = _read_pending(project_root)
    real_intent_id = first_pending["intent-id"]

    # Plant a response with a deliberately wrong intent-id.
    wrong_id = str(uuid.uuid4())
    assert wrong_id != real_intent_id, "uuid4 collision — vanishingly unlikely"
    _write_response(
        project_root,
        {
            "schema-version": 1,
            "intent-id": wrong_id,
            "kind": first_pending["kind"],
            "value": "c",
            "answered-at": _iso_now(),
        },
    )

    # Second invocation → mismatch → exit 1.
    second = _run_engine(project_root)
    assert second.returncode == 1, (
        f"expected exit 1 on intent-id mismatch, got {second.returncode}; "
        f"stderr={second.stderr!r}; stdout={second.stdout!r}"
    )

    # Forensic preservation: BOTH files remain on disk for inspection.
    assert _pending_path(project_root).is_file(), (
        "pending should be preserved after mismatch (forensic per SPEC §3)"
    )
    assert _response_path(project_root).is_file(), (
        "response should be preserved after mismatch (forensic per SPEC §3)"
    )

    # The preserved response still carries the wrong id — engine did not
    # rewrite it.
    preserved_response = json.loads(
        _response_path(project_root).read_text(encoding="utf-8")
    )
    assert preserved_response["intent-id"] == wrong_id
