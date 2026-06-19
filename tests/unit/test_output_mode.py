import io

from engine.ui import output_mode as om


def test_default_mode_is_plain_when_not_tty_and_no_env(monkeypatch):
    monkeypatch.delenv("FORGE_OUTPUT", raising=False)
    stream = io.StringIO()  # not a tty
    assert om.detect_output_mode([], stream=stream) is om.OutputMode.PLAIN


def test_tty_stream_yields_tty_mode(monkeypatch):
    monkeypatch.delenv("FORGE_OUTPUT", raising=False)

    class _TTY(io.StringIO):
        def isatty(self):
            return True

    assert om.detect_output_mode([], stream=_TTY()) is om.OutputMode.TTY


def test_json_meta_flag_in_argv_yields_json(monkeypatch):
    monkeypatch.delenv("FORGE_OUTPUT", raising=False)

    class _TTY(io.StringIO):
        def isatty(self):
            return True

    # --json wins even over a tty — for a read-command in the allowlist.
    assert (
        om.detect_output_mode(["status", "--json"], command="status", stream=_TTY())
        is om.OutputMode.JSON
    )


def test_forge_output_env_yields_json(monkeypatch):
    monkeypatch.setenv("FORGE_OUTPUT", "json")
    assert (
        om.detect_output_mode(["status"], command="status", stream=io.StringIO())
        is om.OutputMode.JSON
    )


def test_forge_output_env_unknown_value_ignored(monkeypatch):
    monkeypatch.setenv("FORGE_OUTPUT", "yaml")  # unsupported → ignored
    assert (
        om.detect_output_mode(["status"], command="status", stream=io.StringIO())
        is om.OutputMode.PLAIN
    )


def test_json_gated_to_read_commands_allowlist(monkeypatch):
    # H-001 — Decisão de design 2 enforced structurally: FORGE_OUTPUT=json on an
    # INTERACTIVE command resolves to PLAIN/TTY, NEVER JSON. The cinematic UX of
    # plan/implement/init/... must not degrade just because the env var is set.
    monkeypatch.setenv("FORGE_OUTPUT", "json")
    for interactive in ("plan", "implement", "init", "reconfigure", "evolve", "qa", "undo", "raw"):
        assert (
            om.detect_output_mode([interactive], command=interactive, stream=io.StringIO())
            is om.OutputMode.PLAIN
        ), f"{interactive} must ignore FORGE_OUTPUT=json (interactive carve-out)"


def test_json_meta_flag_ignored_on_interactive_command(monkeypatch):
    # A spurious --json in argv for an interactive command is ignored too.
    monkeypatch.delenv("FORGE_OUTPUT", raising=False)
    assert (
        om.detect_output_mode(["plan", "--json"], command="plan", stream=io.StringIO())
        is om.OutputMode.PLAIN
    )


def test_all_read_commands_are_json_capable(monkeypatch):
    monkeypatch.setenv("FORGE_OUTPUT", "json")
    for read_cmd in ("status", "doctor", "verify", "memory", "graph"):
        assert (
            om.detect_output_mode([read_cmd], command=read_cmd, stream=io.StringIO())
            is om.OutputMode.JSON
        ), f"{read_cmd} is a read-command and must honour JSON mode"


def test_no_command_falls_back_to_stream_mode(monkeypatch):
    # When command is None (e.g. bare invocation / library caller), JSON is not
    # resolved — the allowlist cannot be satisfied, so we degrade to TTY/PLAIN.
    monkeypatch.setenv("FORGE_OUTPUT", "json")
    assert om.detect_output_mode([], command=None, stream=io.StringIO()) is om.OutputMode.PLAIN


def test_isatty_that_raises_falls_back_to_plain(monkeypatch):
    """C-41 (PR21-I10): um stream cujo isatty() LEVANTA não derruba a resolução —
    cai pra PLAIN (fallback seguro)."""
    class _BadStream(io.StringIO):
        def isatty(self):
            raise OSError("stream fechado")

    monkeypatch.delenv("FORGE_OUTPUT", raising=False)
    assert (
        om.detect_output_mode([], command=None, stream=_BadStream())
        is om.OutputMode.PLAIN
    )


def test_set_get_reset_roundtrip():
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        assert om.get_output_mode() is om.OutputMode.JSON
    finally:
        om.reset_output_mode(token)
    # After reset, back to the unset default (PLAIN).
    assert om.get_output_mode() is om.OutputMode.PLAIN
