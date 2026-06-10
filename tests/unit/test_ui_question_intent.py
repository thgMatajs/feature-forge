"""Unit tests — engine.ui.question in intent-only mode (DRIFT-1 W2.T1).

Validates the refactored chokepoint: each ask* entrypoint either consumes
a matching response from ``.claude/state/forge-response.json`` (returning
the value) or emits a fresh pending intent + raises
``PausedForInputError``. No path through stdin remains in question.py
itself — that lives in ``tty_bridge`` (W3).

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §2, §3, §4, §6
- docs/schemas/intent-protocol.md
- docs/superpowers/plans/drift-1-intent-protocol.md W2.T1
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.ui import intent_state, question


# --- Helpers ---------------------------------------------------------------


def _read_pending(project_root: Path) -> dict:
    """Read forge-pending.json written by question.* into the test project."""
    path = project_root / ".claude" / "state" / "forge-pending.json"
    assert path.is_file(), f"expected pending at {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _write_response(project_root: Path, payload: dict) -> Path:
    """Write a synthetic forge-response.json — simulates the host caller."""
    state_dir = project_root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "forge-response.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _chdir_to_project(monkeypatch, tmp_project_root):
    """Most callsites resolve project_root via cwd — keep tests deterministic."""
    monkeypatch.chdir(tmp_project_root)
    # Make .claude/workflow-config.yaml present so find_project_root works.
    (tmp_project_root / ".claude").mkdir(exist_ok=True)
    (tmp_project_root / ".claude" / "workflow-config.yaml").write_text(
        "schema-version: 1\n", encoding="utf-8"
    )
    yield


# --- PausedForInputError sanity --------------------------------------------


def test_paused_for_input_error_is_exception_subclass():
    """The sentinel must be catchable as a plain Exception by cli.main()."""
    assert issubclass(question.PausedForInputError, Exception)


def test_paused_for_input_error_carries_intent_payload(tmp_project_root):
    """The exception instance exposes the intent dict via ``.intent`` attr."""
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask("Pick:", {"a": "Apple"})
    assert hasattr(exc.value, "intent"), "PausedForInputError must carry .intent"
    assert isinstance(exc.value.intent, dict)
    assert exc.value.intent["kind"] == "ask"
    assert exc.value.intent["question"] == "Pick:"


# --- ask: pending emission --------------------------------------------------


def test_ask_without_response_emits_pending_and_raises(tmp_project_root):
    """No response on disk → write canonical pending JSON, raise sentinel."""
    with pytest.raises(question.PausedForInputError):
        question.ask(
            "Qual preset usar?",
            {"kmp-mobile": "Android + iOS + KMP", "android-only": "Android nativo"},
            default="kmp-mobile",
        )

    payload = _read_pending(tmp_project_root)
    assert payload["schema-version"] == 1
    assert payload["kind"] == "ask"
    assert payload["question"] == "Qual preset usar?"
    assert payload["options"] == {
        "kmp-mobile": "Android + iOS + KMP",
        "android-only": "Android nativo",
    }
    assert payload["default"] == "kmp-mobile"
    assert payload["allow-pause"] is True
    assert isinstance(payload["intent-id"], str) and len(payload["intent-id"]) > 0
    assert isinstance(payload["pid"], int)
    assert "created-at" in payload


def test_ask_with_matching_response_returns_value_and_clears_files(
    tmp_project_root,
):
    """Consume response, return key, delete both pending + response files."""
    # First call emits pending.
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask("Pick:", {"a": "Apple", "b": "Banana"})
    intent_id = exc.value.intent["intent-id"]

    # Host writes response.
    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask",
            "value": "b",
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    # Second call consumes.
    result = question.ask("Pick:", {"a": "Apple", "b": "Banana"})
    assert result == "b"

    # Both state files cleared.
    assert not (tmp_project_root / ".claude" / "state" / "forge-pending.json").exists()
    assert not (tmp_project_root / ".claude" / "state" / "forge-response.json").exists()


def test_ask_rejects_response_value_outside_options(tmp_project_root):
    """A response with a value that is not in options → raise ValueError."""
    # Emit pending first to anchor intent-id.
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask("Pick:", {"a": "Apple"})
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask",
            "value": "not-a-real-key",
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    with pytest.raises(ValueError):
        question.ask("Pick:", {"a": "Apple"})


# --- ask: pause semantics via response --------------------------------------


def test_ask_response_paused_true_raises_prompt_aborted(tmp_project_root):
    """Response with ``paused: true`` and ``allow_pause=True`` (default) →
    PromptAbortedError (preserves legacy semantics).
    """
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask("Pick:", {"a": "Apple"})
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask",
            "paused": True,
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    with pytest.raises(question.PromptAbortedError):
        question.ask("Pick:", {"a": "Apple"})


def test_ask_response_paused_with_allow_pause_false_raises_value_error(
    tmp_project_root,
):
    """``allow_pause=False`` + ``paused: true`` → ValueError (pause forbidden)."""
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask("Pick:", {"a": "Apple"}, allow_pause=False)
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask",
            "paused": True,
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    with pytest.raises(ValueError):
        question.ask("Pick:", {"a": "Apple"}, allow_pause=False)


# --- ask: validation --------------------------------------------------------


def test_ask_empty_options_rejected_no_pending_written(tmp_project_root):
    """Empty options → ValueError, no pending file emitted."""
    with pytest.raises(ValueError):
        question.ask("Pick:", {})
    assert not (
        tmp_project_root / ".claude" / "state" / "forge-pending.json"
    ).exists()


# --- ask_text ---------------------------------------------------------------


def test_ask_text_emits_pending_with_ask_text_kind(tmp_project_root):
    """ask_text writes ``kind: "ask_text"`` and includes default + validator_hint."""
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask_text(
            "Slug:",
            default="my-slug",
            validator=lambda s: len(s) > 0,
            validator_hint="não pode ser vazio",
        )
    intent = exc.value.intent
    assert intent["kind"] == "ask_text"
    assert intent["question"] == "Slug:"
    assert intent["default"] == "my-slug"
    assert intent["validator-hint"] == "não pode ser vazio"


def test_ask_text_response_returns_string(tmp_project_root):
    """A matching string response is returned verbatim."""
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask_text("Slug:")
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask_text",
            "value": "lembrete-rega",
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    assert question.ask_text("Slug:") == "lembrete-rega"


def test_ask_text_response_rejected_by_validator_raises_value_error(
    tmp_project_root,
):
    """If the validator rejects the response, surface ValueError (do not loop)."""
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask_text("Slug:", validator=lambda s: s == "ok", validator_hint="ok")
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask_text",
            "value": "not-ok",
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    with pytest.raises(ValueError):
        question.ask_text("Slug:", validator=lambda s: s == "ok", validator_hint="ok")


# --- ask_multi --------------------------------------------------------------


def test_ask_multi_emits_pending_with_min_selected(tmp_project_root):
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask_multi(
            "Pick many:",
            {"a": "A", "b": "B", "c": "C"},
            min_selected=2,
        )
    intent = exc.value.intent
    assert intent["kind"] == "ask_multi"
    assert intent["options"] == {"a": "A", "b": "B", "c": "C"}
    assert intent["min-selected"] == 2


def test_ask_multi_response_returns_list_in_options_order(tmp_project_root):
    """User picks ``c,a`` but the engine returns options-insertion-order."""
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask_multi("Pick many:", {"a": "A", "b": "B", "c": "C"})
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask_multi",
            "value": ["c", "a"],
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    result = question.ask_multi("Pick many:", {"a": "A", "b": "B", "c": "C"})
    assert result == ["a", "c"]


def test_ask_multi_response_with_invalid_key_raises_value_error(tmp_project_root):
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask_multi("Pick:", {"a": "A", "b": "B"})
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask_multi",
            "value": ["a", "zz"],
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    with pytest.raises(ValueError):
        question.ask_multi("Pick:", {"a": "A", "b": "B"})


# --- confirm ---------------------------------------------------------------


def test_confirm_emits_pending_with_confirm_kind(tmp_project_root):
    with pytest.raises(question.PausedForInputError) as exc:
        question.confirm("Tem certeza?", default=False)
    intent = exc.value.intent
    assert intent["kind"] == "confirm"
    assert intent["question"] == "Tem certeza?"
    assert intent["options"] == {"s": "sim", "n": "não"}
    assert intent["default"] == "n"


def test_confirm_response_bool_true(tmp_project_root):
    with pytest.raises(question.PausedForInputError) as exc:
        question.confirm("Aplicar?")
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "confirm",
            "value": True,
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    assert question.confirm("Aplicar?") is True


def test_confirm_response_string_s_or_n(tmp_project_root):
    """Backward-compat: response may carry "s"/"n" string instead of bool."""
    with pytest.raises(question.PausedForInputError) as exc:
        question.confirm("Aplicar?")
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "confirm",
            "value": "n",
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    assert question.confirm("Aplicar?") is False


# --- ask_three_paths --------------------------------------------------------


def test_ask_three_paths_emits_pending_with_kind_and_three_options(
    tmp_project_root,
):
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask_three_paths(
            "cc-gate",
            paths=[
                {"label": "Refatorar", "motive": "reduce complexity"},
                {"label": "Reverter", "motive": "back out"},
                {"label": "Override-justify", "motive": "commit body"},
            ],
        )
    intent = exc.value.intent
    assert intent["kind"] == "ask_three_paths"
    assert intent["options"] == {
        "a": "Refatorar",
        "b": "Reverter",
        "c": "Override-justify",
    }
    assert "cc-gate" in intent["question"]


def test_ask_three_paths_requires_exactly_three_paths(tmp_project_root):
    with pytest.raises(ValueError):
        question.ask_three_paths(
            "gate",
            paths=[{"label": "A", "motive": ""}, {"label": "B", "motive": ""}],
        )
    # No pending should have been written for the invalid call.
    assert not (
        tmp_project_root / ".claude" / "state" / "forge-pending.json"
    ).exists()


def test_ask_three_paths_response_returns_choice_key(tmp_project_root):
    paths = [
        {"label": "A", "motive": "ma"},
        {"label": "B", "motive": "mb"},
        {"label": "C", "motive": "mc"},
    ]
    with pytest.raises(question.PausedForInputError) as exc:
        question.ask_three_paths("gate", paths=paths)
    intent_id = exc.value.intent["intent-id"]

    _write_response(
        tmp_project_root,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask_three_paths",
            "value": "b",
            "answered-at": "2026-06-10T19:00:00Z",
        },
    )

    assert question.ask_three_paths("gate", paths=paths) == "b"


# --- Race detection integration -------------------------------------------


def test_ask_race_detection_raises_when_pending_recent_other_intent(
    tmp_project_root,
):
    """A recent pending with a different intent-id blocks a new ask emission."""
    recent_iso = (
        datetime.now(timezone.utc) - timedelta(minutes=2)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    state_dir = tmp_project_root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "forge-pending.json").write_text(
        json.dumps(
            {
                "schema-version": 1,
                "intent-id": "stale-but-recent-id",
                "command": "init",
                "command-args": [],
                "kind": "ask",
                "question": "Outra pergunta",
                "options": {"x": "X"},
                "default": None,
                "allow-pause": True,
                "created-at": recent_iso,
                "pid": 99999,
                "checkpoint-path": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(intent_state.RaceDetectedError):
        question.ask("Pergunta nova:", {"a": "A"})


# --- Persistence sanity ----------------------------------------------------


def test_pending_intent_id_stable_across_re_emission(tmp_project_root):
    """Two emissions of the same prompt produce the same intent-id (resume safety)."""
    with pytest.raises(question.PausedForInputError) as first:
        question.ask("Pick:", {"a": "Apple"})
    first_id = first.value.intent["intent-id"]

    # Re-emit same prompt (no response on disk yet, but pending matches).
    with pytest.raises(question.PausedForInputError) as second:
        question.ask("Pick:", {"a": "Apple"})
    second_id = second.value.intent["intent-id"]

    assert first_id == second_id, "same prompt must produce same intent-id"
