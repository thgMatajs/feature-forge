"""Regression test for ``parser_kotlin``'s decl extraction inside strings/comments.

``_RE_DECL`` greedily matched ``fun``/``class``/``object`` everywhere — including
inside Kotlin raw strings (``\"\"\" ... \"\"\"``), regular double-quoted strings,
block comments, and line comments. Those false positives polluted the symbols
list and the duplicates table downstream. See R2.4.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.parser_kotlin import parse_kotlin_file


def _write_kt(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_decl_inside_raw_string_is_ignored(tmp_path: Path) -> None:
    """Top-level ``fun`` inside a raw string literal must not be extracted."""
    src = '''
package demo

val raw = """
fun fake() { TODO() }
class FakeClass { }
"""

fun real() { return }
'''
    p = _write_kt(tmp_path, "Raw.kt", src)
    info = parse_kotlin_file(p)

    names = {s.name for s in info.symbols}
    assert "real" in names, f"legitimate fun real() missing; names={names}"
    assert "fake" not in names, (
        f"false-positive: fun fake() inside raw string was extracted; names={names}"
    )
    assert "FakeClass" not in names, (
        f"false-positive: class FakeClass inside raw string was extracted; names={names}"
    )


def test_decl_inside_block_comment_is_ignored(tmp_path: Path) -> None:
    """``fun`` / ``class`` inside ``/* ... */`` must not be extracted."""
    src = """
package demo

/* fun commented() { TODO() }
   class CommentedClass { }
*/

fun real() { return }
"""
    p = _write_kt(tmp_path, "BlockComment.kt", src)
    info = parse_kotlin_file(p)

    names = {s.name for s in info.symbols}
    assert "real" in names, f"legitimate fun real() missing; names={names}"
    assert "commented" not in names, (
        f"false-positive: fun commented() in block comment was extracted; names={names}"
    )
    assert "CommentedClass" not in names, (
        f"false-positive: class CommentedClass in block comment was extracted; names={names}"
    )


def test_decl_inside_line_comment_is_ignored(tmp_path: Path) -> None:
    """``fun`` after ``//`` must not be extracted."""
    src = """
package demo

// fun lineCommented() { TODO() }
fun real() { return }
"""
    p = _write_kt(tmp_path, "LineComment.kt", src)
    info = parse_kotlin_file(p)

    names = {s.name for s in info.symbols}
    assert "real" in names
    assert "lineCommented" not in names, (
        f"false-positive: fun in line comment was extracted; names={names}"
    )


def test_legitimate_declarations_still_detected(tmp_path: Path) -> None:
    """Regression guard: normal Kotlin with no string/comment shenanigans
    must keep extracting all declarations after the mask change."""
    src = """
package demo

class A { }
object B
interface C
fun d() { }
val e = 1
var f = 2
"""
    p = _write_kt(tmp_path, "Normal.kt", src)
    info = parse_kotlin_file(p)

    names = {s.name for s in info.symbols}
    # All 6 declarations should round-trip.
    assert names == {"A", "B", "C", "d", "e", "f"}, names
