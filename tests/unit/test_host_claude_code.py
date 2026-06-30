"""Unit tests for ``engine.host.adapters.claude_code.ClaudeCodeAdapter``.

Contract verified (spec §4 — Claude Code sequence):

- ``ask()`` first-entry path emits an XML-style ``<FORGE_INTENT .../>``
  self-closing marker on ``sys.stdout`` and raises ``PausedForInputError``.
  The stdout marker IS the pending notification on the CC channel —
  there is NO ``forge-pending.json`` write here. Spec §4 contracts CC
  consumes the marker, dispatches ``AskUserQuestion`` natively, and
  writes ``forge-response.json`` directly.
- Re-entry path (matching response already on disk in the consumed
  log OR response file) consumes the response and returns an
  ``AskResult`` without raising — same idempotency invariant as
  ``IntentFileAdapter`` because the same ``stable_intent_id`` /
  ``intent_state.read_response`` chokepoints are reused.
- ``emit_warn`` and ``emit_progress`` are non-blocking (no exception,
  no pending file written).
- Marker attributes are XML-safe (special chars escaped) — the marker
  must parse as well-formed XML so the CC harness can consume it with
  a standard XML reader.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from engine.host.adapter import AskKind, AskResult, PausedForInputError
from engine.host.adapters.claude_code import ClaudeCodeAdapter


def test_ask_emits_stdout_marker_and_pauses(tmp_path, capsys):
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK,
            question="Tipo da feature?",
            options={"product": "Product feature", "bugfix": "Bug fix"},
            default=None,
            allow_pause=True,
        )
    captured = capsys.readouterr()
    out = captured.out
    assert "<FORGE_INTENT" in out
    assert 'kind="ask"' in out
    assert 'question="Tipo da feature?"' in out
    # Must end with self-closing /> form
    assert "/>" in out

    # CC adapter MUST NOT write pending.json — stdout marker is the channel
    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert not pending.exists()


def test_ask_consumes_cached_response_on_reentry(tmp_path):
    """Pre-populate response.json (simulating CC having asked user). Re-entry returns AskResult.

    Task 0.7a parity: the adapter now resolves ``(command, command_args)``
    via ``_command_context()`` instead of the pre-0.7a hardcoded
    ``("host-adapter", [])``. To keep this test deterministic across
    invocation styles (pytest, IDE runners, CI) we set the contextvar
    to a fixed tuple and compute the expected intent-id against the
    same tuple.
    """
    from engine.ui import intent_state
    from engine.ui.question import _cli_command_context, stable_intent_id
    from engine.utils.paths import forge_state_dir

    state = forge_state_dir(tmp_path)
    state.mkdir(parents=True)

    kind = AskKind.ASK
    question = "Tipo da feature?"
    options = {"product": "Product feature", "bugfix": "Bug fix"}

    token = _cli_command_context.set(("test", []))
    try:
        intent_id = stable_intent_id(
            kind.value,
            question,
            options,
            extra={"default": None, "min-selected": None, "validator-hint": None},
            command="test",
            command_args=[],
        )

        # Simulate CC harness writing the matching response.
        intent_state.write_response(
            tmp_path,
            {
                "schema-version": 1,
                "intent-id": intent_id,
                "value": "product",
            },
            state_dir=state,
        )
        # Reset log cache so the freshly-written response is visible.
        intent_state._reset_log_cache()

        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        result = adapter.ask(
            kind=kind,
            question=question,
            options=options,
            default=None,
            allow_pause=True,
        )
        assert isinstance(result, AskResult)
        assert result.value == "product"
        assert result.paused is False
    finally:
        _cli_command_context.reset(token)


def test_emit_progress_and_warn_non_blocking(tmp_path):
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    adapter.emit_progress(step="planning", total=10, current=3)
    adapter.emit_warn(message="heads up")
    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert not pending.exists()


def test_marker_xml_escapes_special_chars(tmp_path, capsys):
    """Question containing < > & " must produce a well-formed XML marker.

    Validation via stdlib XML parse: the marker must round-trip through
    ``ElementTree.fromstring``, which is stricter than any ad-hoc
    substring check — guarantees no unescaped ``<``/``&``/``"`` leak
    into attribute values and break the CC consumer.
    """
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    tricky = 'Use "X" & validate <input>?'
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK_TEXT,
            question=tricky,
            options={},
            default=None,
            allow_pause=True,
        )
    out = capsys.readouterr().out
    assert "<FORGE_INTENT" in out

    # Extract just the marker line (last non-blank line of stdout).
    marker_line = next(
        line for line in reversed(out.splitlines()) if line.strip().startswith("<FORGE_INTENT")
    )
    # Must parse as well-formed XML.
    elem = ET.fromstring(marker_line)
    assert elem.tag == "FORGE_INTENT"
    assert elem.attrib["kind"] == "ask_text"
    # Round-trip preserves the original (unescaped) value in attrib dict.
    assert elem.attrib["question"] == tricky


# ----------------------------------------------------------------------
# Cross-AI review HIGH — ask_three_paths + confirm on the CC channel
# ----------------------------------------------------------------------


def test_three_paths_emits_marker_and_pauses(tmp_path, capsys):
    """``ASK_THREE_PATHS`` first-entry emits the stdout marker (paths-detail
    JSON-encoded) and raises paused — the CC channel renders the
    3-caminhos block from the marker.
    """
    import json as _json

    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    paths_detail = [
        {"key": "a", "label": "Refatorar", "motive": "reduz complexidade"},
        {"key": "b", "label": "Reverter", "motive": "desfaz o commit"},
        {"key": "c", "label": "Override-justify", "motive": "documenta no commit"},
    ]
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK_THREE_PATHS,
            question="Qual caminho para 'cc-gate'?",
            options={"a": "Refatorar", "b": "Reverter", "c": "Override-justify"},
            default=None,
            allow_pause=True,
            paths_detail=paths_detail,
        )
    out = capsys.readouterr().out
    assert "<FORGE_INTENT" in out
    assert 'kind="ask_three_paths"' in out
    # Marker must remain well-formed XML and surface paths-detail.
    from xml.etree import ElementTree as ET

    marker_line = next(
        line for line in reversed(out.splitlines())
        if line.strip().startswith("<FORGE_INTENT")
    )
    attribs = ET.fromstring(marker_line).attrib
    assert _json.loads(attribs["paths-detail"]) == paths_detail
    # CC channel never writes pending.json — stdout marker is the channel.
    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert not pending.exists()


def test_confirm_emits_marker_and_pauses(tmp_path, capsys):
    """``CONFIRM`` first-entry emits the stdout marker with s/n options."""
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.CONFIRM,
            question="Aplicar?",
            options={"s": "sim", "n": "não"},
            default="n",
            allow_pause=True,
        )
    out = capsys.readouterr().out
    assert "<FORGE_INTENT" in out
    assert 'kind="confirm"' in out
    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert not pending.exists()


def test_confirm_consumes_bool_response_on_reentry(tmp_path):
    """Re-entry on ``CONFIRM`` returns the bool value the host wrote."""
    from engine.ui import intent_state
    from engine.ui.question import _cli_command_context, stable_intent_id
    from engine.utils.paths import forge_state_dir

    state = forge_state_dir(tmp_path)
    state.mkdir(parents=True, exist_ok=True)

    kind = AskKind.CONFIRM
    question = "Aplicar?"
    options = {"s": "sim", "n": "não"}

    token = _cli_command_context.set(("test", []))
    try:
        intent_id = stable_intent_id(
            kind.value,
            question,
            options,
            extra={"default": "n", "min-selected": None, "validator-hint": None},
            command="test",
            command_args=[],
        )
        intent_state.write_response(
            tmp_path,
            {"schema-version": 1, "intent-id": intent_id, "value": True},
            state_dir=state,
        )
        intent_state._reset_log_cache()

        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        result = adapter.ask(
            kind=kind,
            question=question,
            options=options,
            default="n",
            allow_pause=True,
        )
        assert result.value is True
    finally:
        _cli_command_context.reset(token)


# ----------------------------------------------------------------------
# Task 0.7a — parity with question._build_pending
# ----------------------------------------------------------------------


def _extract_marker_attribs(stdout: str) -> dict:
    """Pull attributes off the ``<FORGE_INTENT .../>`` marker via stdlib XML.

    Same parser the CC harness uses on the consumer side — guarantees
    our test assertions reflect what a real harness would observe.
    """
    line = next(
        ln for ln in reversed(stdout.splitlines()) if ln.strip().startswith("<FORGE_INTENT")
    )
    return ET.fromstring(line).attrib


def test_ask_text_validator_hint_changes_intent_id(tmp_path, capsys):
    """HI-002 / MD-001 parity: distinct ``validator_hint`` → distinct intent-id
    in the stdout marker.

    Same invariant as the IntentFileAdapter sibling test; here we
    verify it via the marker attributes (CC adapter does not write
    pending.json).
    """
    adapter = ClaudeCodeAdapter(project_root=tmp_path)

    try:
        adapter.ask_text(prompt="Enter:", default=None, validator_hint="email")
    except PausedForInputError:
        pass
    out_a = capsys.readouterr().out
    attribs_a = _extract_marker_attribs(out_a)
    id_a = attribs_a["intent-id"]
    assert attribs_a["validator-hint"] == "email"

    try:
        adapter.ask_text(prompt="Enter:", default=None, validator_hint="phone")
    except PausedForInputError:
        pass
    out_b = capsys.readouterr().out
    attribs_b = _extract_marker_attribs(out_b)
    id_b = attribs_b["intent-id"]
    assert attribs_b["validator-hint"] == "phone"

    assert id_a != id_b, (
        "validator_hint must enter the intent-id hash; same prompt "
        "with different hints produced identical ids in the marker."
    )


def test_marker_uses_command_context(tmp_path, capsys):
    """HI-002 invariant on the CC channel: the intent-id reflects
    ``_command_context``, not the legacy hardcoded ``("host-adapter", [])``.

    The marker itself does not surface command/command-args (those are
    pending-payload fields), but they DO enter the hash via
    ``stable_intent_id``. We verify by computing the expected id under
    the contextvar and comparing.
    """
    from engine.ui.question import _cli_command_context, stable_intent_id

    token = _cli_command_context.set(("plan", ["IN-42100"]))
    try:
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        with pytest.raises(PausedForInputError):
            adapter.ask(
                kind=AskKind.ASK,
                question="Q?",
                options={"a": "A"},
                default=None,
                allow_pause=True,
            )
        out = capsys.readouterr().out
        attribs = _extract_marker_attribs(out)

        expected_id = stable_intent_id(
            AskKind.ASK.value,
            "Q?",
            {"a": "A"},
            extra={
                "default": None,
                "min-selected": None,
                "validator-hint": None,
            },
            command="plan",
            command_args=["IN-42100"],
        )
        assert attribs["intent-id"] == expected_id
    finally:
        _cli_command_context.reset(token)


def test_marker_omits_optional_attribs_when_none(tmp_path, capsys):
    """Marker attribute parity: ``validator-hint`` / ``min-selected`` /
    ``paths-detail`` appear ONLY when supplied (not None).

    Pre-0.7a the marker had no such attrs at all; with 0.7a they are
    optional, conditional on caller intent. CC parsers that key on
    attribute presence (``"validator-hint" in attribs``) keep working.
    """
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK,
            question="Q?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
        )
    attribs = _extract_marker_attribs(capsys.readouterr().out)
    assert "validator-hint" not in attribs
    assert "min-selected" not in attribs
    assert "paths-detail" not in attribs


def test_marker_includes_optional_attribs_when_supplied(tmp_path, capsys):
    """Inverse of the omit-when-None case: when callers pass extras,
    the marker surfaces them as XML-safe attributes."""
    import json as _json

    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    paths_detail = [{"path": "src/foo.py", "blast": "high"}]
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK_MULTI,
            question="Pick files?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
            min_selected=2,
            validator_hint="email",
            paths_detail=paths_detail,
        )
    attribs = _extract_marker_attribs(capsys.readouterr().out)
    assert attribs["validator-hint"] == "email"
    assert attribs["min-selected"] == "2"
    # paths-detail is JSON-encoded on the wire (same encoding as ``options``).
    assert _json.loads(attribs["paths-detail"]) == paths_detail


# ----------------------------------------------------------------------
# Task 0.7c — pause/cancel propagation + CR-002 state preservation
# ----------------------------------------------------------------------


def test_ask_response_paused_raises_user_paused(tmp_path, capsys):
    """Response with ``paused=true`` triggers ``UserPausedError``.

    CR-001 parity with ``IntentFileAdapter``: even though CC's pending
    channel is the stdout marker (not a pending file), the response
    side of DRIFT-1 is identical — so pause/cancel propagation must
    behave the same way.
    """
    from engine.host.adapter import UserPausedError
    from engine.ui import intent_state
    from engine.ui.question import _cli_command_context, stable_intent_id
    from engine.utils.paths import forge_state_dir

    state = forge_state_dir(tmp_path)
    state.mkdir(parents=True, exist_ok=True)

    kind = AskKind.ASK
    question = "Q?"
    options = {"a": "A"}

    token = _cli_command_context.set(("test", []))
    try:
        intent_id = stable_intent_id(
            kind.value,
            question,
            options,
            extra={"default": None, "min-selected": None, "validator-hint": None},
            command="test",
            command_args=[],
        )
        intent_state.write_response(
            tmp_path,
            {"schema-version": 1, "intent-id": intent_id, "paused": True},
            state_dir=state,
        )
        intent_state._reset_log_cache()

        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        with pytest.raises(UserPausedError):
            adapter.ask(
                kind=kind,
                question=question,
                options=options,
                default=None,
                allow_pause=True,
            )
    finally:
        _cli_command_context.reset(token)


def test_ask_response_cancelled_raises_user_cancelled(tmp_path, capsys):
    """Response with ``cancelled=true`` triggers ``UserCancelledError``.

    CR-003 parity with the fallback adapter — maps to exit 130 at the
    CLI boundary.
    """
    from engine.host.adapter import UserCancelledError
    from engine.ui import intent_state
    from engine.ui.question import _cli_command_context, stable_intent_id
    from engine.utils.paths import forge_state_dir

    state = forge_state_dir(tmp_path)
    state.mkdir(parents=True, exist_ok=True)

    kind = AskKind.ASK
    question = "Q?"
    options = {"a": "A"}

    token = _cli_command_context.set(("test", []))
    try:
        intent_id = stable_intent_id(
            kind.value,
            question,
            options,
            extra={"default": None, "min-selected": None, "validator-hint": None},
            command="test",
            command_args=[],
        )
        intent_state.write_response(
            tmp_path,
            {"schema-version": 1, "intent-id": intent_id, "cancelled": True},
            state_dir=state,
        )
        intent_state._reset_log_cache()

        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        with pytest.raises(UserCancelledError):
            adapter.ask(
                kind=kind,
                question=question,
                options=options,
                default=None,
                allow_pause=True,
            )
    finally:
        _cli_command_context.reset(token)


def test_ask_consume_preserves_state_files_cr_002(tmp_path, capsys):
    """CR-002 — after happy-path consume on CC adapter, response file
    remains on disk for caller cleanup.

    CC adapter doesn't write ``forge-pending.json`` (stdout marker is
    the pending channel), so only ``forge-response.json`` is checked
    here — the pending side never existed in this lifecycle.
    """
    from engine.ui import intent_state
    from engine.ui.question import _cli_command_context, stable_intent_id
    from engine.utils.paths import forge_state_dir

    state = forge_state_dir(tmp_path)
    state.mkdir(parents=True, exist_ok=True)

    kind = AskKind.ASK
    question = "Q?"
    options = {"a": "A"}

    token = _cli_command_context.set(("test", []))
    try:
        intent_id = stable_intent_id(
            kind.value,
            question,
            options,
            extra={"default": None, "min-selected": None, "validator-hint": None},
            command="test",
            command_args=[],
        )
        intent_state.write_response(
            tmp_path,
            {"schema-version": 1, "intent-id": intent_id, "value": "a"},
            state_dir=state,
        )
        intent_state._reset_log_cache()

        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        result = adapter.ask(
            kind=kind,
            question=question,
            options=options,
            default=None,
            allow_pause=True,
        )
        assert result.value == "a"
        # CR-002: response file preserved for forensic / caller cleanup.
        assert (state / "forge-response.json").exists(), (
            "response must survive consume — adapter no longer auto-clears"
        )
    finally:
        _cli_command_context.reset(token)


# ----------------------------------------------------------------------
# BUG-G2/MEM-4 (T2) — marker announces response-schema-version
# ----------------------------------------------------------------------


def test_marker_announces_response_schema_version(tmp_path, capsys):
    """O ``<FORGE_INTENT>`` anuncia ``response-schema-version`` (auto-descritivo).

    BUG-G2/MEM-4: sem o atributo, um host ingênuo omite ``schema-version`` na
    response e toma exit 1 silencioso. O marker agora ensina ao host qual
    versão devolver — sem enfraquecer o leitor estrito da response.
    """
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK,
            question="Tipo da feature?",
            options={"product": "Product feature"},
            default=None,
            allow_pause=True,
        )
    attribs = _extract_marker_attribs(capsys.readouterr().out)
    assert attribs.get("response-schema-version") == "1", (
        "marker não anuncia response-schema-version (BUG-G2/MEM-4)"
    )


def test_marker_schema_version_attr_is_optional_tolerant(tmp_path, capsys):
    """O novo atributo não quebra hosts que parseiam por presença dos antigos."""
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK,
            question="Tipo?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
        )
    attribs = _extract_marker_attribs(capsys.readouterr().out)
    # Atributos canônicos preservados (shape não muda).
    for k in ("kind", "intent-id", "question", "options", "default", "allow-pause"):
        assert k in attribs, f"atributo canônico {k!r} sumiu — shape quebrado"
