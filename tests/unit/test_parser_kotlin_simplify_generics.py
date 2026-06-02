"""Regression: ``_simplify_generics`` terminates on malformed input.

R3.7 guard: defensive hardening of the inner generic-parsing loop in
``engine.graph.parser_kotlin._simplify_generics``. Even though the
current code (with `i += 1` at the bottom) is correct for the cases we
checked, a future edit that inserts a `continue` short-cut could turn
the loop into a hang on inputs like ``List<T`` (unclosed bracket) or
``<<<`` (deep nesting without closures). The hardening adds an
explicit iteration ceiling — this test guards the contract.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from engine.graph.parser_kotlin import _simplify_generics


def _run_with_timeout(fn, args, timeout_seconds: float = 1.0) -> Any:
    """Run fn(*args) on a worker thread; fail the test if it doesn't
    return within timeout_seconds. Threads can't be killed safely, so a
    hang leaves the thread orphaned — but the test still fails fast.
    """
    result: dict[str, Any] = {}
    exc: dict[str, BaseException] = {}

    def target() -> None:
        try:
            result["value"] = fn(*args)
        except BaseException as e:  # noqa: BLE001 — propagate for assertion
            exc["err"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        pytest.fail(
            f"_simplify_generics did not terminate within {timeout_seconds}s — "
            f"infinite loop on input {args!r}"
        )
    if "err" in exc:
        raise exc["err"]
    return result.get("value")


def test_simplify_generics_terminates_on_unclosed_bracket() -> None:
    """An unclosed generic ``List<T`` (no closing >) must not hang."""
    out = _run_with_timeout(_simplify_generics, ("List<T",))
    # Output shape isn't load-bearing for this test — we only assert
    # termination. The result should be a string (gracefully degraded).
    assert isinstance(out, str)


def test_simplify_generics_terminates_on_deep_unclosed_nesting() -> None:
    """Pathological deep nesting ``<<<<<`` must not hang."""
    out = _run_with_timeout(_simplify_generics, ("<<<<<",))
    assert isinstance(out, str)


def test_simplify_generics_terminates_on_mixed_garbage() -> None:
    """Mixed malformed input: opening + identifier + no close."""
    out = _run_with_timeout(_simplify_generics, ("Map<K, List<V",))
    assert isinstance(out, str)


def test_simplify_generics_well_formed_still_works() -> None:
    """Regression guard: well-formed inputs still produce the right shape."""
    # Smoke — the function strips T : Any to T, etc.
    out = _simplify_generics("List<T : Any>")
    assert "T" in out
    # Sanity — the result should still contain the bracket structure.
    assert "<" in out and ">" in out


def test_simplify_generics_empty_input_returns_empty() -> None:
    """Boundary: empty string returns empty (no crash)."""
    assert _simplify_generics("") == ""
