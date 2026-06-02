"""Regression tests for ``engine.graph.duplicates._fingerprint``.

Guards against separator-collision bugs where TypeScript union-type
signatures (containing ``|``) could ambiguate join semantics — see R2.1.
"""

from __future__ import annotations

from engine.graph.duplicates import _fingerprint


def test_fingerprint_avoids_pipe_separator_collision() -> None:
    """Two distinct partitions of the same payload must hash differently.

    With a ``|`` separator, ``["foo|bar", "baz"]`` and ``["foo", "bar|baz"]``
    both serialise to ``foo|bar|baz`` — same hash, false-positive collision.
    The NUL separator (``\\x00``) cannot appear in legal source text, so
    distinct partitions stay distinct.
    """
    a = _fingerprint("foo|bar", "baz")
    b = _fingerprint("foo", "bar|baz")
    assert a != b, (
        "fingerprint collided for distinct partitions sharing the joined payload — "
        "separator must not be a character that may appear inside any part"
    )


def test_fingerprint_is_stable_for_identical_input() -> None:
    """Same inputs produce same hash — basic determinism guard."""
    assert _fingerprint("alpha", "beta") == _fingerprint("alpha", "beta")


def test_fingerprint_handles_ts_union_signature() -> None:
    """Realistic case: TS signature with ``|`` inside one of the parts."""
    fp_with_union = _fingerprint(
        "near-duplicate",
        "shared",
        "",
        "format",
        "(x: string | number) => string",
        "",
    )
    fp_without_union = _fingerprint(
        "near-duplicate",
        "shared",
        "",
        "format",
        "(x: string) => string",
        "",
    )
    assert fp_with_union != fp_without_union
