import io

import pytest

from engine.host.adapter import AskKind, PausedForInputError
from engine.host.adapters.claude_code import ClaudeCodeAdapter
from engine.ui import output_mode as om


def test_interactive_command_resolves_plain_under_forge_output_json(monkeypatch):
    # (c) — under FORGE_OUTPUT=json, an interactive command resolves PLAIN/TTY,
    # never JSON: renderer.write is NOT globally suppressed for it, so its
    # cinematic UX never degrades. This is the structural allowlist guard.
    monkeypatch.setenv("FORGE_OUTPUT", "json")
    assert (
        om.detect_output_mode(["plan", "auth"], command="plan", stream=io.StringIO())
        is om.OutputMode.PLAIN
    )


def test_marker_emitted_under_forge_output_json(tmp_path, monkeypatch, capsys):
    # (a) — the intent marker is written via sys.stdout.write DIRECTLY by the
    # claude_code adapter (engine/host/adapters/claude_code.py::_emit_marker),
    # so it survives regardless of output-mode. Force JSON mode on the context
    # var to prove the marker is NOT swallowed by the renderer.write no-op.
    monkeypatch.setenv("FORGE_OUTPUT", "json")
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        # First entry (no response file) → emit marker, then raise PausedForInputError.
        with pytest.raises(PausedForInputError):
            adapter.ask(
                kind=AskKind.ASK,
                question="Continuar?",
                options={"sim": "Sim", "nao": "Não"},
                default=None,
                allow_pause=True,
            )
    finally:
        om.reset_output_mode(token)
    out = capsys.readouterr().out
    assert "<FORGE_INTENT" in out  # marker survived JSON mode (direct sys.stdout.write)


def test_exit_2_preserved_under_forge_output_json(tmp_path, monkeypatch):
    # (b) — the paused-for-input contract (exit-2 / PausedForInputError) is
    # unchanged under FORGE_OUTPUT=json. The first-entry ask path must still
    # raise PausedForInputError (the engine bubbles it up as exit code 2).
    monkeypatch.setenv("FORGE_OUTPUT", "json")
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        with pytest.raises(PausedForInputError):
            adapter.ask(
                kind=AskKind.ASK,
                question="Continuar?",
                options={"sim": "Sim", "nao": "Não"},
                default=None,
                allow_pause=True,
            )
    finally:
        om.reset_output_mode(token)
