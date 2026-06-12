"""M-07 + M-08 regression: pathspec-backed gitignore must handle edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.graph import builder


def _setup(tmp_path: Path, gitignore: str) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text(gitignore, encoding="utf-8")
    return tmp_path


def test_bracket_class_supported(tmp_path: Path) -> None:
    root = _setup(tmp_path, "[abc].txt\n")
    rules = builder._parse_gitignore(root)
    assert builder._matches_gitignore(root / "a.txt", root, rules, is_dir=False)
    assert not builder._matches_gitignore(root / "d.txt", root, rules, is_dir=False)


def test_escape_hash(tmp_path: Path) -> None:
    root = _setup(tmp_path, r"\#literal" + "\n")
    rules = builder._parse_gitignore(root)
    assert builder._matches_gitignore(root / "#literal", root, rules, is_dir=False)


def test_double_star_middle(tmp_path: Path) -> None:
    root = _setup(tmp_path, "a/**/b\n")
    rules = builder._parse_gitignore(root)
    assert builder._matches_gitignore(root / "a" / "x" / "y" / "b", root, rules, is_dir=False)


def test_glob_pattern_no_prefix_overmatch(tmp_path: Path) -> None:
    """M-08: pattern `foo` must NOT match `foobar` (no suffix overmatch).

    Note: canonical gitignore semantics DO match files inside a directory
    whose name matches the pattern (e.g. `*.kt` matches `foo.kt/bar.java`
    because git ignores the entire `foo.kt/` directory tree). Verified
    via `git check-ignore` against real git. This test guards against
    string-prefix overmatch which is the actual M-08 risk.
    """
    root = _setup(tmp_path, "foo\n")
    rules = builder._parse_gitignore(root)
    assert builder._matches_gitignore(root / "foo", root, rules, is_dir=False)
    assert not builder._matches_gitignore(root / "foobar", root, rules, is_dir=False)
    assert not builder._matches_gitignore(root / "foo.bak", root, rules, is_dir=False)


def test_canonical_gitignore_dir_tree(tmp_path: Path) -> None:
    """Confirm canonical gitignore: `*.kt` matches files inside `foo.kt/` dir.

    This matches `git check-ignore` behavior. Documenting here so reviewers
    don't mistake this for an M-08 regression.
    """
    root = _setup(tmp_path, "*.kt\n")
    rules = builder._parse_gitignore(root)
    target_dir = root / "foo.kt"
    target_dir.mkdir(exist_ok=True)
    (target_dir / "bar.java").write_text("", encoding="utf-8")
    # Canonical git behavior: contents of an ignored directory are ignored.
    assert builder._matches_gitignore(
        target_dir / "bar.java", root, rules, is_dir=False
    )
