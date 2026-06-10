"""Unit tests — engine.ui.tty_bridge.

Validates the subprocess-loop wrapper that drives the engine in
TTY-fallback mode (sub-Q **Sc** of the DRIFT-1 spec). The bridge does
three things — nothing more, nothing less:

1. Runs the engine module as a subprocess.
2. When the subprocess exits 2, reads ``forge-pending.json``, prompts
   the user via stdin (rendered through ``engine.ui.renderer`` and
   ``engine.persona.mentor_calmo``), writes ``forge-response.json``,
   and loops.
3. When the subprocess exits 2 but no pending is on disk (CR-003: the
   user paused via response in a previous iteration and the engine
   cleared state cleanly), terminates the loop without re-prompting.

Subprocess machinery is mocked in this lane — the actual end-to-end
loop driving ``engine.cli`` is W5's job (markers ``integration`` /
``e2e``). Here we test the bridge's control flow in isolation.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §6, §7, §8
- docs/superpowers/plans/drift-1-intent-protocol.md W3.T1
- docs/schemas/intent-protocol.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

import pytest

from engine.ui import intent_state, tty_bridge


# --- Helpers ---------------------------------------------------------------


def _pending_payload(
    *,
    intent_id: str = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    kind: str = "ask",
    question: str = "Qual preset usar pra este projeto?",
    options: dict[str, str] | None = None,
    paths_detail: list[dict[str, str]] | None = None,
    allow_pause: bool = True,
    min_selected: int | None = None,
    default: str | None = None,
) -> dict[str, Any]:
    """Build a minimally-valid pending dict matching docs/schemas/intent-protocol.md."""
    payload: dict[str, Any] = {
        "schema-version": 1,
        "intent-id": intent_id,
        "command": "init",
        "command-args": [],
        "kind": kind,
        "question": question,
        "options": options
        if options is not None
        else {"kmp-mobile": "Android + iOS + KMP shared", "android-only": "Android nativo"},
        "default": default,
        "allow-pause": allow_pause,
        "created-at": "2026-06-10T18:42:11Z",
        "pid": 84210,
        "checkpoint-path": ".claude/.init-checkpoint.yaml",
    }
    if paths_detail is not None:
        payload["paths-detail"] = paths_detail
    if min_selected is not None:
        payload["min-selected"] = min_selected
    return payload


class _FakeCompletedProcess:
    """Stand-in for ``subprocess.CompletedProcess`` — only ``returncode`` matters."""

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def _make_subprocess_run(return_codes: Iterable[int]):
    """Build a ``subprocess.run`` replacement that yields ``return_codes`` in order.

    Tracks invocations on ``.calls`` so tests can assert the loop ran the
    right number of times.
    """
    codes = list(return_codes)
    calls: list[dict[str, Any]] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001 — mirrors subprocess.run signature
        calls.append({"cmd": cmd, "kwargs": kwargs})
        if not codes:
            raise AssertionError(
                "subprocess.run invoked more times than expected return codes provided"
            )
        return _FakeCompletedProcess(codes.pop(0))

    fake_run.calls = calls  # type: ignore[attr-defined]
    fake_run.remaining = codes  # type: ignore[attr-defined]
    return fake_run


# --- Exit-code propagation -------------------------------------------------


def test_main_propagates_exit_0_when_subprocess_succeeds(
    monkeypatch, tmp_project_root, no_color
):
    """rc=0 → bridge returns 0 without prompting (happy path, no pause)."""
    fake_run = _make_subprocess_run([0])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)

    # input() should never be called when no pause occurs.
    def boom(prompt=""):  # noqa: ANN001
        raise AssertionError(f"input() must not be called on exit-0 path (prompt={prompt!r})")

    monkeypatch.setattr("builtins.input", boom)

    rc = tty_bridge.main("engine.cli", ["init"])

    assert rc == 0
    assert len(fake_run.calls) == 1  # type: ignore[attr-defined]


def test_main_propagates_exit_1_when_subprocess_errors(
    monkeypatch, tmp_project_root, no_color
):
    """rc=1 → bridge returns 1 (fatal error from engine)."""
    fake_run = _make_subprocess_run([1])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)

    rc = tty_bridge.main("engine.cli", ["init"])
    assert rc == 1


def test_main_propagates_exit_130_when_subprocess_cancelled(
    monkeypatch, tmp_project_root, no_color
):
    """rc=130 → bridge returns 130 (engine reported user-cancel)."""
    fake_run = _make_subprocess_run([130])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)

    rc = tty_bridge.main("engine.cli", ["init"])
    assert rc == 130


# --- Loop: exit 2 → prompt → response → re-invoke --------------------------


def test_main_prompts_and_writes_response_on_exit_2_with_pending(
    monkeypatch, tmp_project_root, no_color
):
    """exit 2 + pending → prompt user, write response, loop, exit clean."""
    pending = _pending_payload()
    intent_state.write_pending(pending, tmp_project_root)

    fake_run = _make_subprocess_run([2, 0])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("builtins.input", lambda prompt="": "kmp-mobile")

    rc = tty_bridge.main("engine.cli", ["init"])

    assert rc == 0
    # Loop ran twice: paused once, then completed.
    assert len(fake_run.calls) == 2  # type: ignore[attr-defined]

    # Response was written with the correct intent-id + value.
    response_path = tmp_project_root / ".claude" / "state" / "forge-response.json"
    assert response_path.is_file()
    response = json.loads(response_path.read_text(encoding="utf-8"))
    assert response["intent-id"] == pending["intent-id"]
    assert response["value"] == "kmp-mobile"
    assert response["kind"] == "ask"
    assert response["schema-version"] == 1
    assert "answered-at" in response


def test_main_returns_clean_on_exit_2_without_pending(
    monkeypatch, tmp_project_root, no_color
):
    """exit 2 + no pending → engine cleared state (CR-003 user-paused).

    The bridge respects the cleared state — no re-prompt, terminate the
    loop and propagate the user-paused exit code (2). The caller of
    ``tty_bridge`` (``bin/forge`` in W4) maps 2 cleanly to the OS.
    """
    fake_run = _make_subprocess_run([2])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)

    def boom(prompt=""):  # noqa: ANN001
        raise AssertionError("input() must not be called when no pending is present")

    monkeypatch.setattr("builtins.input", boom)

    rc = tty_bridge.main("engine.cli", ["init"])

    # SPEC §8: UserPausedError maps to exit 2; the bridge propagates that
    # outcome verbatim to the OS (no re-prompt loop without pending data).
    assert rc == 2
    assert len(fake_run.calls) == 1  # type: ignore[attr-defined]


# --- Pause-token recognition (Decision 27) ---------------------------------


@pytest.mark.parametrize("token", ["para", "pausa", "quit", "q", "exit", "PARA", "Pausa"])
def test_pause_token_produces_paused_response(
    token, monkeypatch, tmp_project_root, no_color
):
    """Tokens ``para``/``pausa``/``quit``/``q``/``exit`` (any case) → paused response.

    Faithful to the real engine: after the bridge writes a paused response,
    the next engine subprocess invocation consumes it, hits ``UserPausedError``
    (CR-003), clears state, and exits 2. The bridge then sees "exit 2 with no
    pending" → terminates cleanly.
    """
    pending = _pending_payload()
    intent_state.write_pending(pending, tmp_project_root)

    state_dir = tmp_project_root / ".claude" / "state"
    pending_path = state_dir / "forge-pending.json"
    response_path = state_dir / "forge-response.json"

    captured_response: dict[str, Any] = {}

    call_count = {"n": 0}

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First invocation — engine emits pending (already on disk) + exits 2.
            return _FakeCompletedProcess(2)
        # Second invocation — engine consumes the paused response, clears state.
        if response_path.exists():
            captured_response.update(json.loads(response_path.read_text(encoding="utf-8")))
        if pending_path.exists():
            pending_path.unlink()
        if response_path.exists():
            response_path.unlink()
        return _FakeCompletedProcess(2)  # UserPausedError → exit 2

    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("builtins.input", lambda prompt="": token)

    rc = tty_bridge.main("engine.cli", ["init"])

    assert rc == 2  # UserPausedError propagated
    assert captured_response.get("paused") is True
    assert captured_response["intent-id"] == pending["intent-id"]
    assert "value" not in captured_response or captured_response["value"] in (None, "")


# --- Ctrl+C handling -------------------------------------------------------


def test_keyboard_interrupt_during_prompt_returns_130(
    monkeypatch, tmp_project_root, no_color
):
    """KeyboardInterrupt during the stdin prompt → exit 130 + state cleared (Decision 27)."""
    pending = _pending_payload()
    intent_state.write_pending(pending, tmp_project_root)

    fake_run = _make_subprocess_run([2])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)

    def raise_kbi(prompt=""):  # noqa: ANN001
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_kbi)

    rc = tty_bridge.main("engine.cli", ["init"])

    assert rc == 130
    # State files cleared on cancel — no residue.
    pending_path = tmp_project_root / ".claude" / "state" / "forge-pending.json"
    response_path = tmp_project_root / ".claude" / "state" / "forge-response.json"
    assert not pending_path.exists()
    assert not response_path.exists()


# --- ask_three_paths rendering ---------------------------------------------


def test_ask_three_paths_renders_paths_detail(
    monkeypatch, tmp_project_root, no_color, capsys, deterministic_persona
):
    """When kind == ask_three_paths, the canonical 3-caminhos block is rendered."""
    paths_detail = [
        {"key": "a", "label": "Refatorar pra reduzir complexidade", "motive": "reduz risco"},
        {"key": "b", "label": "Reverter o commit", "motive": "preserva baseline"},
        {"key": "c", "label": "Override-justify via commit body", "motive": "destrava o gate"},
    ]
    pending = _pending_payload(
        intent_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        kind="ask_three_paths",
        question="Qual caminho para resolver 'cc-gate-threshold-exceeded'?",
        options={
            "a": "Refatorar pra reduzir complexidade",
            "b": "Reverter o commit",
            "c": "Override-justify via commit body",
        },
        paths_detail=paths_detail,
    )
    intent_state.write_pending(pending, tmp_project_root)

    fake_run = _make_subprocess_run([2, 0])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("builtins.input", lambda prompt="": "a")

    tty_bridge.main("engine.cli", ["verify"])

    rendered = capsys.readouterr().out
    # Canonical block markers (mentor_calmo.three_paths_block).
    assert "🛑" in rendered
    assert "Três caminhos pra resolver" in rendered
    assert "Refatorar pra reduzir complexidade" in rendered
    assert "Reverter o commit" in rendered
    assert "Override-justify via commit body" in rendered
    assert "reduz risco" in rendered


# --- ask_multi: list response ----------------------------------------------


def test_ask_multi_response_splits_comma_separated_input(
    monkeypatch, tmp_project_root, no_color
):
    """Comma-separated stdin → list[str] response value."""
    pending = _pending_payload(
        intent_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        kind="ask_multi",
        question="Quais propostas aceitar?",
        options={"p1": "Proposta 1", "p2": "Proposta 2", "p3": "Proposta 3"},
        min_selected=1,
    )
    intent_state.write_pending(pending, tmp_project_root)

    fake_run = _make_subprocess_run([2, 0])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("builtins.input", lambda prompt="": "p1, p3")

    tty_bridge.main("engine.cli", ["evolve"])

    response_path = tmp_project_root / ".claude" / "state" / "forge-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    assert response["value"] == ["p1", "p3"]
    assert response["kind"] == "ask_multi"


# --- confirm: yes/no -------------------------------------------------------


@pytest.mark.parametrize(
    "user_input, expected",
    [
        ("s", True),
        ("sim", True),
        ("y", True),
        ("yes", True),
        ("n", False),
        ("não", False),
        ("nao", False),
        ("no", False),
    ],
)
def test_confirm_response_carries_yes_no_value(
    user_input, expected, monkeypatch, tmp_project_root, no_color
):
    """confirm kind → response carries a bool value normalised from typed token."""
    pending = _pending_payload(
        intent_id=f"dddddddd-dddd-4ddd-8ddd-ddddddddddd{hash(user_input) % 10}",
        kind="confirm",
        question="Tem certeza?",
        options={"s": "sim", "n": "não"},
        default="n",
        allow_pause=False,
    )
    intent_state.write_pending(pending, tmp_project_root)

    fake_run = _make_subprocess_run([2, 0])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("builtins.input", lambda prompt="": user_input)

    tty_bridge.main("engine.cli", ["undo"])

    response_path = tmp_project_root / ".claude" / "state" / "forge-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    assert response["value"] is expected
    assert response["kind"] == "confirm"


# --- ask_text: free-text ---------------------------------------------------


def test_ask_text_returns_typed_string_verbatim(
    monkeypatch, tmp_project_root, no_color
):
    """ask_text → stdin string flows through to response.value untouched."""
    pending = _pending_payload(
        intent_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        kind="ask_text",
        question="Caminho do diretório:",
        options=None,
        default=".claude/cards/local",
    )
    intent_state.write_pending(pending, tmp_project_root)

    fake_run = _make_subprocess_run([2, 0])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("builtins.input", lambda prompt="": "custom/path")

    tty_bridge.main("engine.cli", ["reconfigure"])

    response_path = tmp_project_root / ".claude" / "state" / "forge-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    assert response["value"] == "custom/path"
    assert response["kind"] == "ask_text"


# --- Subprocess env wiring --------------------------------------------------


def test_subprocess_invocation_sets_internal_env_marker(
    monkeypatch, tmp_project_root, no_color
):
    """``FORGE_INTERNAL_TTY_BRIDGE=1`` is set on the spawned subprocess.

    SPEC §6 — engine may use this for logging / debug. Behaviour stays
    identical regardless, but the contract is observable from the env.
    """
    fake_run = _make_subprocess_run([0])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)

    tty_bridge.main("engine.cli", ["init"])

    call = fake_run.calls[0]  # type: ignore[attr-defined]
    env = call["kwargs"].get("env") or {}
    assert env.get("FORGE_INTERNAL_TTY_BRIDGE") == "1"


def test_subprocess_invocation_passes_argv_verbatim(
    monkeypatch, tmp_project_root, no_color
):
    """The user-supplied argv reaches the engine subprocess unchanged."""
    fake_run = _make_subprocess_run([0])
    monkeypatch.setattr(tty_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_project_root)

    tty_bridge.main("engine.cli", ["plan", "lembrete-rega", "--phase", "design"])

    call = fake_run.calls[0]  # type: ignore[attr-defined]
    cmd = call["cmd"]
    # cmd shape: [python_executable, "-m", "engine.cli", "plan", "lembrete-rega", ...]
    assert "engine.cli" in cmd
    plan_idx = cmd.index("engine.cli") + 1
    assert cmd[plan_idx:] == ["plan", "lembrete-rega", "--phase", "design"]


# --- Companion helpers in intent_state (added in W3) -----------------------


def test_intent_state_read_pending_returns_none_when_absent(tmp_project_root):
    """read_pending → None when no pending file is on disk."""
    assert intent_state.read_pending(tmp_project_root) is None


def test_intent_state_read_pending_returns_payload_when_present(tmp_project_root):
    """read_pending → the decoded dict when the file is present."""
    payload = _pending_payload()
    intent_state.write_pending(payload, tmp_project_root)
    result = intent_state.read_pending(tmp_project_root)
    assert result == payload


def test_intent_state_write_response_atomically_writes_canonical_path(tmp_project_root):
    """write_response lands at ``.claude/state/forge-response.json`` atomically."""
    response = {
        "schema-version": 1,
        "intent-id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "kind": "ask",
        "value": "kmp-mobile",
        "answered-at": "2026-06-10T18:42:18Z",
    }
    intent_state.write_response(tmp_project_root, response)

    target = tmp_project_root / ".claude" / "state" / "forge-response.json"
    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8")) == response
    # No .tmp leftover (atomic write contract).
    leftovers = [p for p in target.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
