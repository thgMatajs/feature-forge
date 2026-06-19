"""Unit tests — engine.ui.intent_state.

Validates the state-file chokepoint for the DRIFT-1 intent protocol:
write_pending, read_response, clear_intent_files, detect_race, plus
IntentMismatchError and RaceDetectedError exception classes.

DRIFT-1 W1.T3 — foundation for the engine/ui/question.py refactor (W2).
This module never touches question.py; it is invoked from there.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §2, §3, §9
- docs/schemas/intent-protocol.md
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.ui import intent_state


# --- Helpers ---------------------------------------------------------------


def _pending_payload(*, intent_id: str = "11111111-1111-4111-8111-111111111111",
                     created_at: str | None = None,
                     pid: int = 84210) -> dict:
    """A minimally-valid pending dict matching the canonical schema.

    ``pid`` defaults to a synthetic value (84210). Tests que esperam que
    ``detect_race`` levante ``RaceDetectedError`` em pending recente devem
    passar ``pid=os.getpid()`` — desde STALE-1 (W-DEBT), ``detect_race`` faz
    ``os.kill(pid, 0)`` e varre pendings de PID morto em vez de declarar race.
    """
    return {
        "schema-version": 1,
        "intent-id": intent_id,
        "command": "init",
        "command-args": [],
        "kind": "ask",
        "question": "Qual preset?",
        "options": {"kmp-mobile": "Android + iOS + KMP shared"},
        "default": "kmp-mobile",
        "allow-pause": True,
        "created-at": created_at or "2026-06-10T18:42:11Z",
        "pid": pid,
        "checkpoint-path": ".claude/.init-checkpoint.yaml",
    }


def _response_payload(*, intent_id: str, value: object = "kmp-mobile",
                      kind: str = "ask") -> dict:
    return {
        "schema-version": 1,
        "intent-id": intent_id,
        "kind": kind,
        "value": value,
        "answered-at": "2026-06-10T18:42:18Z",
    }


def _read_disk(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- write_pending ---------------------------------------------------------


def test_write_pending_creates_state_file_at_canonical_path(tmp_project_root):
    payload = _pending_payload()
    intent_state.write_pending(payload, tmp_project_root)

    target = tmp_project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    assert target.is_file(), "pending file must land at .claude/forge/state/forge-pending.json"
    assert _read_disk(target) == payload


def test_write_pending_creates_parent_dirs(tmp_project_root):
    """state/ dir is created on demand — fresh project may have only .git."""
    state_dir = tmp_project_root / ".claude" / "forge" / "state"
    assert not state_dir.exists()

    intent_state.write_pending(_pending_payload(), tmp_project_root)
    assert state_dir.is_dir()


def test_write_pending_is_atomic_no_tmp_leftover(tmp_project_root):
    """No .tmp file may remain after a successful write."""
    intent_state.write_pending(_pending_payload(), tmp_project_root)
    state_dir = tmp_project_root / ".claude" / "forge" / "state"
    leftovers = [p for p in state_dir.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_write_pending_overwrites_existing(tmp_project_root):
    """A second write with the same intent-id replaces the file in place."""
    intent_state.write_pending(_pending_payload(), tmp_project_root)
    second = _pending_payload()
    second["question"] = "Outra pergunta?"
    intent_state.write_pending(second, tmp_project_root)

    target = tmp_project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    assert _read_disk(target)["question"] == "Outra pergunta?"


# --- read_response ---------------------------------------------------------


def test_read_response_returns_none_when_file_absent(tmp_project_root):
    """No response yet → caller treats as 'pause needed'."""
    assert intent_state.read_response(tmp_project_root, intent_id="anything") is None


def test_read_response_returns_dict_when_intent_id_matches(tmp_project_root):
    intent_id = "22222222-2222-4222-8222-222222222222"
    response_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-response.json"
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(_response_payload(intent_id=intent_id)),
        encoding="utf-8",
    )

    result = intent_state.read_response(tmp_project_root, intent_id=intent_id)
    assert result is not None
    assert result["intent-id"] == intent_id
    assert result["value"] == "kmp-mobile"


def test_read_response_raises_on_intent_id_mismatch(tmp_project_root):
    """Mismatched intent-id is forensic: do NOT silently delete; raise."""
    written_id = "33333333-3333-4333-8333-333333333333"
    expected_id = "44444444-4444-4444-8444-444444444444"

    response_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-response.json"
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(_response_payload(intent_id=written_id)),
        encoding="utf-8",
    )

    with pytest.raises(intent_state.IntentMismatchError) as exc:
        intent_state.read_response(tmp_project_root, intent_id=expected_id)
    assert written_id in str(exc.value)
    assert expected_id in str(exc.value)
    # File preserved for forensic inspection.
    assert response_path.exists()


def test_read_response_stale_consumed_file_returns_none(tmp_project_root):
    """Multi-Q re-entry: file holds an id already consumed this lifecycle.

    Sequência sob host real (subprocess) em comando que faz 2+ perguntas
    na mesma invocação (ex.: reconfigure backend submenu):

      1. ask(id-A) → file id-A → match → consumed-log ganha id-A. File
         NÃO é limpo (cli.py finally limpa só no fim da invocação).
      2. handler avança → ask(id-B). File ainda tem id-A. id-B não está
         no log, nem no file.

    O file (id-A) já foi CONSUMIDO neste lifecycle — é stale, não um
    mismatch genuíno. Deve retornar None pro caller emitir pending(id-B)
    + exit 2 (handshake normal), NÃO levantar IntentMismatchError.
    """
    intent_state._reset_log_cache()
    consumed_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    fresh_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    # id-A já consumido neste lifecycle (está no log).
    intent_state._append_intent_log(
        tmp_project_root,
        intent_id=consumed_id,
        response=_response_payload(intent_id=consumed_id),
    )
    # File on-disk ainda carrega o id-A (não foi limpo entre as perguntas).
    response_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-response.json"
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(
        json.dumps(_response_payload(intent_id=consumed_id)),
        encoding="utf-8",
    )

    # Pergunta nova (id-B): não está no log nem no file → stale, return None.
    result = intent_state.read_response(tmp_project_root, intent_id=fresh_id)
    assert result is None, (
        "file id já consumido no log deve ser tratado como stale (None), "
        "não como mismatch"
    )
    # File preservado — o caller decide o ciclo de limpeza.
    assert response_path.exists()


def test_read_response_genuine_mismatch_still_raises_when_file_id_not_logged(
    tmp_project_root,
):
    """Mismatch genuíno preserva o comportamento forense.

    File tem id-X que NÃO está no log; request id-Y. Como id-X nunca foi
    consumido neste lifecycle, é resposta órfã/inesperada → ainda
    IntentMismatchError (preserva valor forense). Guard stale-consumido
    NÃO afrouxa este caso.
    """
    intent_state._reset_log_cache()
    file_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    requested_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"

    response_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-response.json"
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(_response_payload(intent_id=file_id)),
        encoding="utf-8",
    )

    with pytest.raises(intent_state.IntentMismatchError) as exc:
        intent_state.read_response(tmp_project_root, intent_id=requested_id)
    assert file_id in str(exc.value)
    assert requested_id in str(exc.value)
    assert response_path.exists()


def test_read_response_raises_on_malformed_json(tmp_project_root):
    response_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-response.json"
    response_path.parent.mkdir(parents=True)
    response_path.write_text("{ not valid json", encoding="utf-8")

    # Any IO error here is upstream's problem; surface it cleanly.
    with pytest.raises(Exception):  # JsonIOError or its subclass
        intent_state.read_response(tmp_project_root, intent_id="anything")


# --- clear_intent_files ----------------------------------------------------


def test_clear_intent_files_deletes_both(tmp_project_root):
    state_dir = tmp_project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True)
    pending = state_dir / "forge-pending.json"
    response = state_dir / "forge-response.json"
    pending.write_text("{}", encoding="utf-8")
    response.write_text("{}", encoding="utf-8")

    intent_state.clear_intent_files(tmp_project_root)
    assert not pending.exists()
    assert not response.exists()


def test_clear_intent_files_idempotent_when_absent(tmp_project_root):
    """No files present is not an error — just a no-op."""
    intent_state.clear_intent_files(tmp_project_root)  # should not raise


def test_clear_intent_files_deletes_only_one_when_only_one_present(tmp_project_root):
    state_dir = tmp_project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True)
    pending = state_dir / "forge-pending.json"
    pending.write_text("{}", encoding="utf-8")

    intent_state.clear_intent_files(tmp_project_root)
    assert not pending.exists()


# --- detect_race -----------------------------------------------------------


def test_detect_race_returns_none_when_no_pending(tmp_project_root):
    """Clean slate — caller may proceed to write a new pending."""
    assert intent_state.detect_race(tmp_project_root, new_intent_id="any") is None


def test_detect_race_returns_none_when_existing_pending_matches(tmp_project_root):
    """Same intent-id is a re-emission, not a race."""
    intent_id = "55555555-5555-4555-8555-555555555555"
    intent_state.write_pending(_pending_payload(intent_id=intent_id), tmp_project_root)
    assert intent_state.detect_race(tmp_project_root, new_intent_id=intent_id) is None


def test_detect_race_sweeps_stale_pending_over_10_minutes(tmp_project_root):
    """A pending older than 10min is treated as orphaned — deleted, then proceed."""
    stale_iso = (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    intent_state.write_pending(
        _pending_payload(
            intent_id="66666666-6666-4666-8666-666666666666",
            created_at=stale_iso,
        ),
        tmp_project_root,
    )
    pending_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    assert pending_path.exists()

    # Different intent-id, but the previous is stale → sweep, return None.
    assert (
        intent_state.detect_race(tmp_project_root, new_intent_id="new-id-here")
        is None
    )
    assert not pending_path.exists(), "stale pending must have been swept"


def test_detect_race_raises_on_recent_concurrent_intent(tmp_project_root):
    """Recent pending with different intent-id → race; surface clearly."""
    recent_iso = (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    existing_id = "77777777-7777-4777-8777-777777777777"
    live_pid = os.getpid()
    intent_state.write_pending(
        _pending_payload(intent_id=existing_id, created_at=recent_iso, pid=live_pid),
        tmp_project_root,
    )

    with pytest.raises(intent_state.RaceDetectedError) as exc:
        intent_state.detect_race(tmp_project_root, new_intent_id="other-id")
    message = str(exc.value)
    # Mensagem mentor-calmo precisa apontar o PID e o path forense.
    # PID vivo (o próprio processo do teste) — STALE-1 só declara race se vivo.
    assert str(live_pid) in message
    assert "forge-pending.json" in message
    # Pending preservado (não sobrescreve).
    assert (tmp_project_root / ".claude" / "forge" / "state" / "forge-pending.json").exists()


def test_detect_race_sweeps_pending_already_consumed_in_log(tmp_project_root):
    """Multi-Q leftover: existing pending's id já consumido → sweep, not race.

    Simétrico ao guard stale-consumido de read_response. Em comandos que
    fazem 2+ perguntas na mesma invocação, o pending da pergunta 1
    sobrevive no disco até o cleanup final. Ao emitir o pending da
    pergunta 2 (id-B), o pending 1 (id-A) ainda está parqueado — mas como
    a resposta de id-A já foi consumida (está no log), é leftover, não uma
    invocação concorrente. detect_race deve varrer e seguir, NÃO levantar
    RaceDetectedError.
    """
    intent_state._reset_log_cache()
    consumed_id = "88888888-8888-4888-8888-888888888888"
    fresh_id = "99999999-9999-4999-8999-999999999999"

    # id-A já consumido neste lifecycle (está no log).
    intent_state._append_intent_log(
        tmp_project_root,
        intent_id=consumed_id,
        response=_response_payload(intent_id=consumed_id),
    )
    # Pending recente da pergunta 1 (id-A) ainda parqueado no disco.
    recent_iso = (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    intent_state.write_pending(
        _pending_payload(intent_id=consumed_id, created_at=recent_iso),
        tmp_project_root,
    )
    pending_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    assert pending_path.exists()

    # Emitir pending da pergunta 2 (id-B) → não é race, é leftover → sweep.
    assert intent_state.detect_race(tmp_project_root, new_intent_id=fresh_id) is None
    assert not pending_path.exists(), (
        "pending já consumido (id no log) deve ser varrido, não tratado como race"
    )


def test_detect_race_handles_pending_missing_created_at(tmp_project_root):
    """Malformed pending (no created-at) is treated as stale — safer to sweep."""
    state_dir = tmp_project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True)
    broken = state_dir / "forge-pending.json"
    broken.write_text(json.dumps({"intent-id": "abc"}), encoding="utf-8")

    # No raise; sweep + proceed.
    assert intent_state.detect_race(tmp_project_root, new_intent_id="new") is None
    assert not broken.exists()


# --- exception sanity ------------------------------------------------------


def test_intent_mismatch_error_is_runtime_error_subclass():
    assert issubclass(intent_state.IntentMismatchError, RuntimeError)


def test_race_detected_error_is_runtime_error_subclass():
    assert issubclass(intent_state.RaceDetectedError, RuntimeError)


# --- schema-version validation (PR #11 finding #4) -------------------------


def test_read_response_raises_on_schema_version_mismatch(tmp_project_root):
    """Response with a foreign schema-version surfaces a typed error, not
    a silent miscompat. File is preserved for inspection."""
    intent_id = "88888888-8888-4888-8888-888888888888"
    response_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-response.json"
    response_path.parent.mkdir(parents=True)
    payload = _response_payload(intent_id=intent_id)
    payload["schema-version"] = 99
    response_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(intent_state.SchemaVersionMismatchError) as exc:
        intent_state.read_response(tmp_project_root, intent_id=intent_id)
    message = str(exc.value)
    assert "99" in message
    assert "1" in message  # current _SCHEMA_VERSION rendered for the user
    # Forensic preservation — the file does not disappear on raise.
    assert response_path.exists()


def test_read_response_passes_with_current_schema_version(tmp_project_root):
    """Happy path: schema-version=1 + matching intent-id round-trips cleanly."""
    intent_id = "99999999-9999-4999-8999-999999999999"
    response_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-response.json"
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(_response_payload(intent_id=intent_id)),
        encoding="utf-8",
    )

    result = intent_state.read_response(tmp_project_root, intent_id=intent_id)
    assert result is not None
    assert result["schema-version"] == 1


# --- clock-skew handling (PR #11 finding #17) ------------------------------


def test_parse_created_at_tolerates_small_future_skew(tmp_project_root):
    """`created-at` slightly in the future (NTP jitter) → still treated as
    a recent pending; race must surface instead of being swept."""
    future_iso = (datetime.now(timezone.utc) + timedelta(seconds=30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    existing_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    intent_state.write_pending(
        _pending_payload(
            intent_id=existing_id, created_at=future_iso, pid=os.getpid()
        ),
        tmp_project_root,
    )

    with pytest.raises(intent_state.RaceDetectedError):
        intent_state.detect_race(tmp_project_root, new_intent_id="brand-new")
    # Pending preservado — small skew is tolerated, not swept.
    assert (
        tmp_project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    ).exists()


def test_parse_created_at_treats_large_future_skew_as_stale(tmp_project_root):
    """`created-at` far in the future → clock is clearly invalid; sweep so the
    lane does not stay parked indefinitely."""
    far_future_iso = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    intent_state.write_pending(
        _pending_payload(
            intent_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            created_at=far_future_iso,
        ),
        tmp_project_root,
    )
    pending_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    assert pending_path.exists()

    assert (
        intent_state.detect_race(tmp_project_root, new_intent_id="next")
        is None
    )
    assert not pending_path.exists(), "large future skew must be swept"


# --- RaceDetectedError 3-caminhos message (PR #11 finding #22) -------------


def test_race_detected_error_message_includes_three_paths(tmp_project_root):
    """Mensagem do gate carrega o bloco canônico de 3 caminhos do projeto."""
    recent_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    intent_state.write_pending(
        _pending_payload(
            intent_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            created_at=recent_iso,
            pid=os.getpid(),
        ),
        tmp_project_root,
    )

    with pytest.raises(intent_state.RaceDetectedError) as exc:
        intent_state.detect_race(tmp_project_root, new_intent_id="rival")
    message = str(exc.value)
    assert "Três caminhos" in message
    assert "rm" in message and "forge-pending.json" in message
    assert "forge undo" in message


# --- specific exception catch in detect_race (PR #11 finding #26) ----------


def test_detect_race_propagates_non_io_exceptions(
    tmp_project_root, monkeypatch
):
    """Programming errors (ValueError, TypeError, ...) escape detect_race
    instead of being silently swallowed and turned into a sweep."""
    state_dir = tmp_project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True)
    pending_path = state_dir / "forge-pending.json"
    pending_path.write_text("{}", encoding="utf-8")

    def _explode(_path):
        raise ValueError("synthetic programming error")

    monkeypatch.setattr(intent_state.json_io, "read_json", _explode)

    with pytest.raises(ValueError, match="synthetic programming error"):
        intent_state.detect_race(tmp_project_root, new_intent_id="x")
    # Pending preservado — não foi feito sweep silencioso pelo broad except.
    assert pending_path.exists()


# --- consumed-intent log (W7-fix re-entry idempotency, 2026-06-12) ---------


def _write_response_file(project_root: Path, payload: dict) -> Path:
    """Drop a synthetic forge-response.json — simulates the host caller."""
    state_dir = project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "forge-response.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _log_file(project_root: Path) -> Path:
    return project_root / ".claude" / "forge" / "state" / "forge-intent-log.jsonl"


def test_read_response_caches_consumed_response_in_log(tmp_project_root):
    """First consume of intent-id appends an entry to forge-intent-log.jsonl."""
    intent_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    _write_response_file(tmp_project_root, _response_payload(intent_id=intent_id))

    result = intent_state.read_response(tmp_project_root, intent_id=intent_id)
    assert result is not None
    assert result["intent-id"] == intent_id

    log = _log_file(tmp_project_root)
    assert log.exists(), "consumed-intent log must be created on first consume"
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, f"one consume → one log entry, got {lines!r}"
    entry = json.loads(lines[0])
    assert entry["intent-id"] == intent_id
    assert entry["response"]["intent-id"] == intent_id
    assert "consumed-at" in entry


def test_read_response_returns_cached_on_re_entry(tmp_project_root):
    """Second read of the same intent-id returns the cached response even
    after the underlying response file has been removed."""
    intent_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    response_path = _write_response_file(
        tmp_project_root, _response_payload(intent_id=intent_id, value="x")
    )

    first = intent_state.read_response(tmp_project_root, intent_id=intent_id)
    assert first is not None

    # Caller (question.py) cleared the response file after consume.
    response_path.unlink()
    assert not response_path.exists()

    # Re-entry: handler re-runs from the top, hits the same ask(), which
    # asks again for intent-id. Without the log this would return None and
    # the handler would emit a duplicate pending. With the log we return
    # the cached response and the handler progresses past this ask().
    cached = intent_state.read_response(tmp_project_root, intent_id=intent_id)
    assert cached is not None
    assert cached["intent-id"] == intent_id
    assert cached["value"] == "x"


def test_read_response_idempotent_after_file_overwrite(tmp_project_root):
    """Multi-intent re-entry scenario: log holds intent A while file holds
    intent B. Reading A returns cached; reading B reads file fresh."""
    intent_a = "11111111-aaaa-4aaa-8aaa-111111111111"
    intent_b = "22222222-bbbb-4bbb-8bbb-222222222222"

    # Phase 1: caller wrote response for A, engine consumes.
    _write_response_file(
        tmp_project_root, _response_payload(intent_id=intent_a, value="a")
    )
    first = intent_state.read_response(tmp_project_root, intent_id=intent_a)
    assert first["value"] == "a"

    # Phase 2: question.py clears file post-consume; caller writes response
    # for the NEXT intent (B).
    (tmp_project_root / ".claude" / "forge" / "state" / "forge-response.json").unlink()
    _write_response_file(
        tmp_project_root, _response_payload(intent_id=intent_b, value="b")
    )

    # Re-entry: handler re-runs from the top, hits ask() for intent A
    # again. Log lookup wins → cached response for A is returned, file is
    # untouched.
    again_a = intent_state.read_response(tmp_project_root, intent_id=intent_a)
    assert again_a["value"] == "a", (
        "log lookup must return cached value for intent-id A even when "
        "the response file holds intent-id B"
    )

    # Handler progresses past ask() for A, hits ask() for B. Now the log
    # has no entry for B; file holds B; consume succeeds.
    fresh_b = intent_state.read_response(tmp_project_root, intent_id=intent_b)
    assert fresh_b["value"] == "b"


def test_read_response_still_raises_mismatch_for_unknown_id(tmp_project_root):
    """When neither log nor file knows the requested intent-id, mismatch
    still fires — the log only short-circuits *cached* hits, not unknowns."""
    written_id = "33333333-cccc-4ccc-8ccc-333333333333"
    expected_id = "44444444-dddd-4ddd-8ddd-444444444444"

    _write_response_file(
        tmp_project_root, _response_payload(intent_id=written_id)
    )

    with pytest.raises(intent_state.IntentMismatchError) as exc:
        intent_state.read_response(tmp_project_root, intent_id=expected_id)
    assert written_id in str(exc.value)
    assert expected_id in str(exc.value)


def test_read_response_none_when_log_empty_and_file_absent(tmp_project_root):
    """No log, no file → caller must emit a fresh pending. Idempotency does
    not invent responses out of thin air."""
    intent_id = "55555555-eeee-4eee-8eee-555555555555"
    assert (
        intent_state.read_response(tmp_project_root, intent_id=intent_id)
        is None
    )
    # Negative invariant: no log file leaked into existence.
    assert not _log_file(tmp_project_root).exists()


def test_clear_intent_files_preserves_log_by_default(tmp_project_root):
    """Per-prompt cleanup in question.py keeps the log alive — re-entry
    idempotency depends on the log surviving across per-ask clears."""
    intent_id = "66666666-ffff-4fff-8fff-666666666666"
    _write_response_file(tmp_project_root, _response_payload(intent_id=intent_id))
    intent_state.read_response(tmp_project_root, intent_id=intent_id)
    assert _log_file(tmp_project_root).exists()

    intent_state.clear_intent_files(tmp_project_root)
    assert _log_file(tmp_project_root).exists(), (
        "default clear must NOT touch the log — re-entry needs it alive"
    )


def test_clear_intent_files_also_log_resets(tmp_project_root):
    """``also_log=True`` exists for callers that already wanted full cleanup
    plus the log in one shot — the top-level handler in engine/cli.py does
    NOT use this path (see ``clear_intent_log_only`` below) but the option
    is here for completeness."""
    intent_id = "77777777-1111-4aaa-8aaa-777777777777"
    _write_response_file(tmp_project_root, _response_payload(intent_id=intent_id))
    intent_state.read_response(tmp_project_root, intent_id=intent_id)
    assert _log_file(tmp_project_root).exists()

    intent_state.clear_intent_files(tmp_project_root, also_log=True)
    assert not _log_file(tmp_project_root).exists(), (
        "also_log=True must delete the consumed-intent log"
    )


def test_clear_intent_log_only_preserves_pending_and_response(tmp_project_root):
    """The lifecycle clear at top-level handler exit MUST preserve pending
    and response (SPEC §3 forensic-preservation on error). Only the log
    goes away."""
    intent_id = "88888888-2222-4bbb-8bbb-888888888888"
    response_path = _write_response_file(
        tmp_project_root, _response_payload(intent_id=intent_id)
    )
    pending_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    pending_path.write_text(
        json.dumps(_pending_payload(intent_id=intent_id)), encoding="utf-8"
    )
    intent_state.read_response(tmp_project_root, intent_id=intent_id)
    assert _log_file(tmp_project_root).exists()

    intent_state.clear_intent_log_only(tmp_project_root)

    assert not _log_file(tmp_project_root).exists(), "log must be gone"
    assert pending_path.exists(), (
        "pending must be preserved — SPEC §3 forensic preservation"
    )
    assert response_path.exists(), (
        "response must be preserved — SPEC §3 forensic preservation"
    )


def test_clear_intent_log_only_idempotent_when_log_absent(tmp_project_root):
    """No log to clear is fine — idempotent."""
    intent_state.clear_intent_log_only(tmp_project_root)  # should not raise


def test_read_response_re_entry_sequence_resolves_without_mismatch(
    tmp_project_root,
):
    """End-to-end simulation of the pre-fix bug: subprocess 1 consumes A,
    caller writes B, subprocess 2 re-enters and asks for A again. Before
    the fix this raised IntentMismatchError; with the log it resolves."""
    intent_a = "88888888-2222-4bbb-8bbb-888888888888"
    intent_b = "99999999-3333-4ccc-8ccc-999999999999"

    # Subprocess 1: response file holds A; engine consumes; question.py
    # clears the file at end of ask().
    _write_response_file(
        tmp_project_root, _response_payload(intent_id=intent_a, value="alpha")
    )
    assert intent_state.read_response(tmp_project_root, intent_id=intent_a) is not None
    (tmp_project_root / ".claude" / "forge" / "state" / "forge-response.json").unlink()

    # Engine emits pending for B → exit 2. Caller writes B's response and
    # re-invokes forge.
    _write_response_file(
        tmp_project_root, _response_payload(intent_id=intent_b, value="beta")
    )

    # Subprocess 2: handler restarts from the top, hits ask() for A first.
    # WITHOUT the log: response file holds B, mismatch → exit 1 → BUG.
    # WITH the log: cached A returned; handler progresses to B.
    a_again = intent_state.read_response(tmp_project_root, intent_id=intent_a)
    assert a_again is not None and a_again["value"] == "alpha"

    b_now = intent_state.read_response(tmp_project_root, intent_id=intent_b)
    assert b_now is not None and b_now["value"] == "beta"


def test_intent_log_tolerates_malformed_lines(tmp_project_root):
    """Crash mid-write may leave a partial JSONL line. Reader must skip
    silently and surface still-good entries."""
    state_dir = tmp_project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True)
    log = state_dir / "forge-intent-log.jsonl"
    good_id = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
    good_entry = {
        "intent-id": good_id,
        "response": {"intent-id": good_id, "value": "ok"},
        "consumed-at": "2026-06-12T00:00:00+00:00",
    }
    log.write_text(
        "\n".join(
            [
                json.dumps(good_entry),
                "{ not valid json",  # partial / corrupt line
                "",  # blank line
                json.dumps({"no-intent-id": "field"}),  # entry shape invalid
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cached = intent_state.read_response(tmp_project_root, intent_id=good_id)
    assert cached is not None
    assert cached["value"] == "ok"


# --- _append_intent_log flush durability (PR #13 review #3405254528) -------


def test_append_intent_log_flushes_after_write(tmp_project_root, monkeypatch):
    """``_append_intent_log`` must call ``file.flush()`` after writing.

    Docstring contract: 'JSONL append + flush is the durability contract'.
    Without an explicit flush, the entry sits in the Python buffer until
    close — which `with` handles for short-lived calls, but a long-lived
    forge process re-reading the log mid-flight (multi-intent re-entry)
    could miss a freshly-appended entry. Regression guard for the missing
    ``f.flush()`` call observed in PR #13 review.
    """
    events: list[tuple[str, object]] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)
        original_flush = handle.flush
        original_close = handle.close

        def spy_flush() -> None:
            events.append(("flush", self))
            original_flush()

        def spy_close() -> None:
            events.append(("close", self))
            original_close()

        handle.flush = spy_flush  # type: ignore[method-assign]
        handle.close = spy_close  # type: ignore[method-assign]
        return handle

    monkeypatch.setattr(Path, "open", tracking_open)

    intent_state._append_intent_log(
        tmp_project_root,
        intent_id="ffffffff-ffff-4fff-8fff-ffffffffffff",
        response={"schema-version": 1, "value": "probe"},
    )

    log_path = tmp_project_root / ".claude" / "forge" / "state" / "forge-intent-log.jsonl"
    log_events = [evt for evt in events if evt[1] == log_path]
    # Must observe an explicit flush BEFORE the close. ``with`` already
    # flushes implicitly on close; the durability contract is the
    # *explicit* mid-block flush so a long-lived process re-reading
    # the log mid-flight observes the entry without waiting for close.
    flush_indices = [i for i, evt in enumerate(log_events) if evt[0] == "flush"]
    close_indices = [i for i, evt in enumerate(log_events) if evt[0] == "close"]
    assert flush_indices, f"no flush() on {log_path}; events={log_events!r}"
    assert close_indices, f"no close() on {log_path}; events={log_events!r}"
    assert min(flush_indices) < min(close_indices), (
        f"flush must precede close (durability contract); events={log_events!r}"
    )
