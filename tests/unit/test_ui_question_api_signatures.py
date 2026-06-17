"""Signature preservation gate — DRIFT-1 W2.T1 (AC-4).

The chokepoint refactor in W2 changes the *internals* of
``engine.ui.question`` but the 5 entrypoints (ask / ask_text / ask_multi
/ confirm / ask_three_paths) must keep bit-a-bit identical signatures so
the 125 callsites across 10 engine modules stay intact.

This test pins the signatures captured pre-refactor. If a future change
needs to alter any signature, that requires a deliberate decision +
update of both the spec and the callsite audit — not a silent edit.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §6 (AC-4)
- docs/superpowers/plans/drift-1-intent-protocol.md W2.T1 anti-padrões
"""

from __future__ import annotations

import inspect

import pytest

from engine.ui import question


# Signatures captured post Task 0.7b. The three delegated entrypoints
# (``ask``/``ask_multi``/``ask_text``) gained a new keyword-only
# ``project_root: Path | None = None`` parameter so callers in tests +
# harnesses can pin the I/O anchor without monkey-patching ``cwd``.
# The first-positional + pre-existing keyword arguments are preserved
# bit-for-bit, so the 108 production callsites continue to compile and
# run untouched (none of them pass ``project_root``).
#
# ``ask_three_paths`` and ``confirm`` remain on the legacy native path
# (not delegated by 0.7b scope) and keep their original signatures.
_EXPECTED_SIGNATURES = {
    "ask": "(question: 'str', options: 'Mapping[str, str]', *, default: 'str | None' = None, allow_pause: 'bool' = True, project_root: 'Path | None' = None) -> 'str'",
    "ask_multi": "(question: 'str', options: 'Mapping[str, str]', *, min_selected: 'int' = 0, project_root: 'Path | None' = None) -> 'list[str]'",
    "ask_text": "(question: 'str', *, default: 'str | None' = None, validator: 'Callable[[str], bool] | None' = None, validator_hint: 'str | None' = None, project_root: 'Path | None' = None) -> 'str'",
    "ask_three_paths": "(gate_name: 'str', paths: 'Sequence[Mapping[str, str]]') -> 'str'",
    "confirm": "(question: 'str', *, default: 'bool' = False, allow_pause: 'bool' = True) -> 'bool'",
}


@pytest.mark.parametrize("fn_name,expected", sorted(_EXPECTED_SIGNATURES.items()))
def test_question_api_signature_preserved(fn_name: str, expected: str):
    fn = getattr(question, fn_name)
    actual = str(inspect.signature(fn))
    assert actual == expected, (
        f"signature drift on question.{fn_name}: "
        f"expected {expected!r}, got {actual!r}"
    )


def test_question_module_exports_all_five_entrypoints():
    """Sanity: the names callers depend on must still resolve."""
    for name in ("ask", "ask_text", "ask_multi", "confirm", "ask_three_paths"):
        assert hasattr(question, name), f"question.{name} missing"


def test_question_module_exports_legacy_exceptions():
    """``PromptAbortedError`` and ``NonInteractiveError`` are part of the
    surface — callers ``except`` them. They survive the refactor.
    """
    assert hasattr(question, "PromptAbortedError")
    assert hasattr(question, "NonInteractiveError")
    assert issubclass(question.PromptAbortedError, RuntimeError)
    assert issubclass(question.NonInteractiveError, RuntimeError)


def test_question_module_exports_new_sentinel():
    """``PausedForInputError`` is the new sentinel for the intent protocol."""
    assert hasattr(question, "PausedForInputError")
    assert issubclass(question.PausedForInputError, Exception)


def test_confirm_default_signature_keeps_pause_allowed():
    """Regression for master-review finding #18 (PR #11).

    A SPEC §2.1 trazia um exemplo com ``allow-pause: false`` para
    ``confirm``, criando drift com a implementação que sempre permitia
    pause. A decisão do orchestrator foi fixar a IMPL como canônica:
    ``confirm`` aceita ``allow_pause`` como kwarg e seu default é
    ``True`` (igual aos demais entrypoints). Esse teste trava o default
    para evitar regressão silenciosa em direção a ``False``.
    """
    sig = inspect.signature(question.confirm)
    assert "allow_pause" in sig.parameters, (
        "confirm() must expose allow_pause as an explicit kwarg "
        "(master review #18 of PR #11)"
    )
    assert sig.parameters["allow_pause"].default is True, (
        "confirm(allow_pause=...) default must remain True; "
        "see master review #18 of PR #11 for the decision rationale"
    )


def test_pause_tokens_preserved():
    """``_PAUSE_TOKENS`` remains module-private but its values must not drift —
    they are documented in the spec § Decision 27 narrative.
    """
    assert hasattr(question, "_PAUSE_TOKENS")
    assert question._PAUSE_TOKENS == {"para", "pausa", "quit", "q", "exit"}
