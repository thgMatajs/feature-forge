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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.ui import intent_state


# --- Helpers ---------------------------------------------------------------


def _pending_payload(*, intent_id: str = "11111111-1111-4111-8111-111111111111",
                     created_at: str | None = None) -> dict:
    """A minimally-valid pending dict matching the canonical schema."""
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
        "pid": 84210,
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

    target = tmp_project_root / ".claude" / "state" / "forge-pending.json"
    assert target.is_file(), "pending file must land at .claude/state/forge-pending.json"
    assert _read_disk(target) == payload


def test_write_pending_creates_parent_dirs(tmp_project_root):
    """state/ dir is created on demand — fresh project may have only .git."""
    state_dir = tmp_project_root / ".claude" / "state"
    assert not state_dir.exists()

    intent_state.write_pending(_pending_payload(), tmp_project_root)
    assert state_dir.is_dir()


def test_write_pending_is_atomic_no_tmp_leftover(tmp_project_root):
    """No .tmp file may remain after a successful write."""
    intent_state.write_pending(_pending_payload(), tmp_project_root)
    state_dir = tmp_project_root / ".claude" / "state"
    leftovers = [p for p in state_dir.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_write_pending_overwrites_existing(tmp_project_root):
    """A second write with the same intent-id replaces the file in place."""
    intent_state.write_pending(_pending_payload(), tmp_project_root)
    second = _pending_payload()
    second["question"] = "Outra pergunta?"
    intent_state.write_pending(second, tmp_project_root)

    target = tmp_project_root / ".claude" / "state" / "forge-pending.json"
    assert _read_disk(target)["question"] == "Outra pergunta?"


# --- read_response ---------------------------------------------------------


def test_read_response_returns_none_when_file_absent(tmp_project_root):
    """No response yet → caller treats as 'pause needed'."""
    assert intent_state.read_response(tmp_project_root, intent_id="anything") is None


def test_read_response_returns_dict_when_intent_id_matches(tmp_project_root):
    intent_id = "22222222-2222-4222-8222-222222222222"
    response_path = tmp_project_root / ".claude" / "state" / "forge-response.json"
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

    response_path = tmp_project_root / ".claude" / "state" / "forge-response.json"
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


def test_read_response_raises_on_malformed_json(tmp_project_root):
    response_path = tmp_project_root / ".claude" / "state" / "forge-response.json"
    response_path.parent.mkdir(parents=True)
    response_path.write_text("{ not valid json", encoding="utf-8")

    # Any IO error here is upstream's problem; surface it cleanly.
    with pytest.raises(Exception):  # JsonIOError or its subclass
        intent_state.read_response(tmp_project_root, intent_id="anything")


# --- clear_intent_files ----------------------------------------------------


def test_clear_intent_files_deletes_both(tmp_project_root):
    state_dir = tmp_project_root / ".claude" / "state"
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
    state_dir = tmp_project_root / ".claude" / "state"
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
    pending_path = tmp_project_root / ".claude" / "state" / "forge-pending.json"
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
    intent_state.write_pending(
        _pending_payload(intent_id=existing_id, created_at=recent_iso),
        tmp_project_root,
    )

    with pytest.raises(intent_state.RaceDetectedError) as exc:
        intent_state.detect_race(tmp_project_root, new_intent_id="other-id")
    message = str(exc.value)
    # Mensagem mentor-calmo precisa apontar o PID e o path forense.
    assert "84210" in message  # pid from _pending_payload
    assert "forge-pending.json" in message
    # Pending preservado (não sobrescreve).
    assert (tmp_project_root / ".claude" / "state" / "forge-pending.json").exists()


def test_detect_race_handles_pending_missing_created_at(tmp_project_root):
    """Malformed pending (no created-at) is treated as stale — safer to sweep."""
    state_dir = tmp_project_root / ".claude" / "state"
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
