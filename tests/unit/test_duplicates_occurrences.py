"""Regression test for ``_parse_occurrences`` / ``_parse_near_duplicate_occurrences``.

POSIX paths may legally contain commas. The GROUP_CONCAT default separator
of ``,`` ambiguates against such paths, mangling the parsed occurrence
list. The fix switches to ``\\x1F`` (Unit Separator) — invisible, cannot
appear in paths — see R2.2.
"""

from __future__ import annotations

from engine.graph.duplicates import (
    _parse_near_duplicate_occurrences,
    _parse_occurrences,
)


def test_parse_occurrences_handles_comma_in_path() -> None:
    """Path with comma must round-trip intact after the new separator change."""
    # Two findings, paths each containing a comma. Joined with the new \x1F separator.
    csv = (
        "1:42:src/a, b.kt"
        "\x1f"
        "2:100:src/c, d.kt"
    )
    items = _parse_occurrences(csv)
    assert items == [
        {"file_id": 1, "line": 42, "path": "src/a, b.kt"},
        {"file_id": 2, "line": 100, "path": "src/c, d.kt"},
    ]


def test_parse_occurrences_handles_simple_paths() -> None:
    """Counter-test: paths without commas still parse cleanly."""
    csv = "1:42:src/foo.kt\x1f2:100:src/bar.kt"
    items = _parse_occurrences(csv)
    assert items == [
        {"file_id": 1, "line": 42, "path": "src/foo.kt"},
        {"file_id": 2, "line": 100, "path": "src/bar.kt"},
    ]


def test_parse_occurrences_empty_input() -> None:
    assert _parse_occurrences(None) == []
    assert _parse_occurrences("") == []


def test_parse_near_duplicate_occurrences_handles_comma_in_path() -> None:
    """Near-duplicate variant carries body_hash too; same separator change."""
    csv = (
        "1:42:abc123:src/x, y.kt"
        "\x1f"
        "2:88:_none_:src/z, w.kt"
    )
    items = _parse_near_duplicate_occurrences(csv)
    assert items == [
        {"file_id": 1, "line": 42, "body_hash": "abc123", "path": "src/x, y.kt"},
        {"file_id": 2, "line": 88, "body_hash": None, "path": "src/z, w.kt"},
    ]


def test_parse_near_duplicate_occurrences_simple() -> None:
    csv = "1:42:abc:src/foo.kt"
    items = _parse_near_duplicate_occurrences(csv)
    assert items == [
        {"file_id": 1, "line": 42, "body_hash": "abc", "path": "src/foo.kt"}
    ]
