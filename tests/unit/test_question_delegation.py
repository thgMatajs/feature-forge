"""Delegation tests — Task 0.7b (v1.3 pilot-ready).

``question.ask`` / ``question.ask_multi`` / ``question.ask_text`` now
delegate their bodies to the resolved ``HostAdapter``. These tests pin
that delegation contract:

1. The delegate calls the adapter's method (and only that method) on
   the happy path.
2. The three adapter exceptions ``PausedForInputError``
   ``UserPausedError`` / ``UserCancelledError`` are wrapped back into
   the ``question.*`` equivalents so the cli.py exception ladder keeps
   working unchanged.
3. Post-consume validation in the delegate still rejects values that
   the adapter accepted but that violate the question-level contract
   (e.g. ``value not in options``) — CR-002 state preservation is
   exercised in the on-disk integration tests under
   ``test_ui_question_intent.py``.

Refs:
- docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md §2 / §4
- docs/superpowers/plans/2026-06-16-v1-3-pilot-ready.md Task 0.7b
- Adapter contract: engine/host/adapter.py
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from engine.ui import question
from engine.host.adapter import (
    AskKind,
    AskResult,
    PausedForInputError as AdapterPaused,
    UserPausedError as AdapterUserPaused,
    UserCancelledError as AdapterUserCancelled,
)


# --- ask -------------------------------------------------------------------


def test_ask_delegates_to_resolved_adapter(tmp_path):
    """Happy path: ``question.ask`` calls ``adapter.ask`` exactly once with
    the canonical kwargs and returns ``AskResult.value`` to the caller.
    """
    mock_adapter = MagicMock()
    mock_adapter.ask.return_value = AskResult(value="product")
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        result = question.ask(
            "Tipo da feature?",
            {"product": "Product", "bugfix": "Bug fix"},
            project_root=tmp_path,
        )
    mock_adapter.ask.assert_called_once()
    call_kwargs = mock_adapter.ask.call_args.kwargs
    assert call_kwargs["kind"] == AskKind.ASK
    assert call_kwargs["question"] == "Tipo da feature?"
    assert call_kwargs["options"] == {"product": "Product", "bugfix": "Bug fix"}
    assert result == "product"


def test_ask_wraps_adapter_paused_as_question_paused(tmp_path):
    """``AdapterPaused`` → ``question.PausedForInputError`` (sentinel for cli exit 2)."""
    mock_adapter = MagicMock()
    mock_adapter.ask.side_effect = AdapterPaused("adapter paused")
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        with pytest.raises(question.PausedForInputError) as exc_info:
            question.ask("Q?", {"a": "A"}, project_root=tmp_path)
    # The wrapped exception carries the intent payload so cli.main keeps
    # the existing emit-and-exit semantics.
    assert exc_info.value.intent["kind"] == "ask"
    assert exc_info.value.intent["question"] == "Q?"


def test_ask_wraps_adapter_user_paused_as_question_user_paused(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.ask.side_effect = AdapterUserPaused("user paused")
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        with pytest.raises(question.UserPausedError):
            question.ask("Q?", {"a": "A"}, project_root=tmp_path)


def test_ask_wraps_adapter_cancelled_as_question_cancelled(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.ask.side_effect = AdapterUserCancelled("cancelled")
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        with pytest.raises(question.UserCancelledError):
            question.ask("Q?", {"a": "A"}, project_root=tmp_path)


def test_ask_rejects_value_not_in_options(tmp_path):
    """Post-consume validation: adapter value outside options raises
    ``ValueError`` (CR-002 — state is preserved by the adapter; the
    delegate just surfaces the validation failure).
    """
    mock_adapter = MagicMock()
    mock_adapter.ask.return_value = AskResult(value="invalid-key")
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        with pytest.raises(ValueError, match="not one of the offered options"):
            question.ask(
                "Q?", {"a": "A", "b": "B"}, project_root=tmp_path,
            )


def test_ask_user_paused_with_allow_pause_false_raises_value_error(tmp_path):
    """``allow_pause=False`` + adapter UserPaused → ValueError (legacy
    "pause forbidden" semantic preserved by the delegate wrapper).
    """
    mock_adapter = MagicMock()
    mock_adapter.ask.side_effect = AdapterUserPaused("user paused")
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        with pytest.raises(ValueError, match="pause not allowed"):
            question.ask(
                "Q?", {"a": "A"}, allow_pause=False, project_root=tmp_path,
            )


# --- ask_text --------------------------------------------------------------


def test_ask_text_delegates_to_resolved_adapter(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.ask_text.return_value = "my answer"
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        result = question.ask_text(
            "Prompt?", default="defval", project_root=tmp_path
        )
    mock_adapter.ask_text.assert_called_once()
    call_kwargs = mock_adapter.ask_text.call_args.kwargs
    assert call_kwargs["prompt"] == "Prompt?"
    assert call_kwargs["default"] == "defval"
    assert result == "my answer"


def test_ask_text_applies_python_validator_post_delegate(tmp_path):
    """The Python-callable ``validator`` is applied by the delegate (not the
    adapter, which only knows ``validator_hint`` over the wire).
    """
    mock_adapter = MagicMock()
    mock_adapter.ask_text.return_value = "not-ok"
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        with pytest.raises(ValueError):
            question.ask_text(
                "Prompt?",
                validator=lambda s: s == "ok",
                validator_hint="must be 'ok'",
                project_root=tmp_path,
            )


def test_ask_text_wraps_adapter_paused(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.ask_text.side_effect = AdapterPaused("paused")
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        with pytest.raises(question.PausedForInputError):
            question.ask_text("Slug:", project_root=tmp_path)


# --- ask_multi -------------------------------------------------------------


def test_ask_multi_delegates_to_resolved_adapter(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.ask_multi.return_value = ["a", "c"]
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        result = question.ask_multi(
            "Choose?",
            {"a": "A", "b": "B", "c": "C"},
            project_root=tmp_path,
        )
    mock_adapter.ask_multi.assert_called_once()
    call_kwargs = mock_adapter.ask_multi.call_args.kwargs
    assert call_kwargs["question"] == "Choose?"
    assert call_kwargs["options"] == {"a": "A", "b": "B", "c": "C"}
    # ``ask_multi`` reprojects on options order before returning.
    assert result == ["a", "c"]


def test_ask_multi_rejects_invalid_keys(tmp_path):
    """Post-consume validation: adapter returns a list with a key that is
    not in options → ``ValueError`` (state-preservation by adapter).
    """
    mock_adapter = MagicMock()
    mock_adapter.ask_multi.return_value = ["a", "zz"]
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        with pytest.raises(ValueError):
            question.ask_multi(
                "Choose?", {"a": "A", "b": "B"}, project_root=tmp_path,
            )


def test_ask_multi_wraps_adapter_user_cancelled(tmp_path):
    mock_adapter = MagicMock()
    mock_adapter.ask_multi.side_effect = AdapterUserCancelled("cancelled")
    with patch.object(question, "_resolve_adapter", return_value=mock_adapter):
        with pytest.raises(question.UserCancelledError):
            question.ask_multi(
                "Choose?", {"a": "A", "b": "B"}, project_root=tmp_path,
            )
