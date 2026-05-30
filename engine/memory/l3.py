"""L3 — read-only proxy over Claude Code auto-memory.

L3 lives at `~/.claude/projects/{project-key}/memory/MEMORY.md` plus sibling
markdown entries. forge never writes here (see docs/schemas/memory.md §L3) —
this module exists purely to expose the user's preferences/feedback to
planning-conductor at session entry.

Resolution strategy:
- Prefer the per-project subdirectory derived from the project root path.
- Fall back to the most-recently-modified `MEMORY.md` under
  `~/.claude/projects/` if no exact match is found (common when Claude
  Code's path-hashing scheme drifts).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from engine.memory import MemoryError
from engine.utils.paths import find_project_root, try_find_project_root

# ── Constants ────────────────────────────────────────────────────────────────

_CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
_MEMORY_DIR_NAME = "memory"
_MEMORY_INDEX_NAME = "MEMORY.md"

# Bullet line shape used by Claude auto-memory:
#   - [Title](file.md) — hook description
# We tolerate em-dash, hyphen, and double-hyphen separators.
_BULLET_RE = re.compile(
    r"^\s*-\s*\[(?P<title>[^\]]+)\]\((?P<file>[^)]+)\)\s*[—\-–]+\s*(?P<hook>.+?)\s*$"
)

# YAML frontmatter delimiter at start of file.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


# ── Path resolution ──────────────────────────────────────────────────────────


def _project_key_from_root(project_root: Path) -> str:
    """Mirror Claude Code's directory naming for ~/.claude/projects/.

    Claude Code encodes the absolute project path by replacing `/` with `-`
    and stripping the leading separator (e.g. `/Users/foo/bar` →
    `-Users-foo-bar`). We replicate that so the canonical key is the first
    candidate when probing.
    """
    return "-" + str(project_root.resolve()).strip("/").replace("/", "-")


def auto_memory_index_path() -> Path:
    """Resolve the most plausible MEMORY.md path; raises MemoryError if none.

    Order of attempts:
      1. Project-matched directory based on CWD's project root.
      2. Most recently modified MEMORY.md anywhere under ~/.claude/projects/.
    """
    if not _CLAUDE_PROJECTS_DIR.exists():
        raise MemoryError(
            f"Claude auto-memory root not found at {_CLAUDE_PROJECTS_DIR}"
        )

    project_root = try_find_project_root() or Path.cwd()
    candidate = (
        _CLAUDE_PROJECTS_DIR
        / _project_key_from_root(project_root)
        / _MEMORY_DIR_NAME
        / _MEMORY_INDEX_NAME
    )
    if candidate.is_file():
        return candidate

    # Fallback: scan for any MEMORY.md, return the most recently modified one.
    candidates = sorted(
        _CLAUDE_PROJECTS_DIR.glob(f"*/{_MEMORY_DIR_NAME}/{_MEMORY_INDEX_NAME}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]

    raise MemoryError(
        f"no {_MEMORY_INDEX_NAME} found under {_CLAUDE_PROJECTS_DIR}"
    )


def _safe_auto_memory_index_path() -> Optional[Path]:
    try:
        return auto_memory_index_path()
    except MemoryError:
        return None


# ── Index parsing ────────────────────────────────────────────────────────────


def read_l3_index() -> list[dict[str, str]]:
    """Parse the MEMORY.md bullet list. Returns `[]` when index is missing.

    Each entry: `{"title": ..., "file": ..., "hook": ...}`. Lines that do not
    match the bullet shape are skipped silently (tolerant by design — L3 is
    user-owned).
    """
    path = _safe_auto_memory_index_path()
    if path is None:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    entries: list[dict[str, str]] = []
    for line in text.splitlines():
        m = _BULLET_RE.match(line)
        if m:
            entries.append(
                {
                    "title": m.group("title").strip(),
                    "file": m.group("file").strip(),
                    "hook": m.group("hook").strip(),
                }
            )
    return entries


def read_l3_entry(entry_file: str) -> Optional[dict[str, Any]]:
    """Read a single auto-memory entry: YAML frontmatter + body.

    `entry_file` is relative to the memory directory holding MEMORY.md.
    Returns None if the file does not exist. The result is
    `{"frontmatter": dict|None, "body": str}`.
    """
    index_path = _safe_auto_memory_index_path()
    if index_path is None:
        return None
    target = (index_path.parent / entry_file).resolve()
    # Constrain to the memory directory to prevent path escape.
    if not str(target).startswith(str(index_path.parent.resolve())):
        return None
    if not target.is_file():
        return None

    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return None

    frontmatter: Optional[dict[str, Any]] = None
    body = text
    m = _FRONTMATTER_RE.match(text)
    if m:
        try:
            parsed = yaml.safe_load(m.group(1))
            if isinstance(parsed, dict):
                frontmatter = parsed
        except yaml.YAMLError:
            frontmatter = None
        body = m.group(2)

    return {"frontmatter": frontmatter, "body": body}


def search_l3(query: str) -> list[dict[str, Any]]:
    """Substring (case-insensitive) match over hook + body. Returns matched entries.

    Each result extends the index entry with `body` so callers don't have to
    re-read. Useful for prompt builders selecting which feedback files to
    inject into context packs.
    """
    if not query:
        return []
    needle = query.casefold()
    results: list[dict[str, Any]] = []
    for idx in read_l3_index():
        if needle in idx["hook"].casefold() or needle in idx["title"].casefold():
            extra = read_l3_entry(idx["file"]) or {"frontmatter": None, "body": ""}
            merged = {**idx, "frontmatter": extra["frontmatter"], "body": extra["body"]}
            results.append(merged)
            continue
        # Body scan only if needed.
        extra = read_l3_entry(idx["file"])
        if extra and needle in extra["body"].casefold():
            merged = {**idx, **extra}
            results.append(merged)
    return results


# Intentionally NO write helpers — L3 is read-only per design.

# Helpers for testability — exported so smoke-tests can pin a fake root.
def _override_projects_dir_for_test(path: Path) -> None:
    """Test-only hook to redirect the projects dir. Not for production use."""
    global _CLAUDE_PROJECTS_DIR  # noqa: PLW0603
    _CLAUDE_PROJECTS_DIR = path


__all__ = [
    "auto_memory_index_path",
    "read_l3_index",
    "read_l3_entry",
    "search_l3",
]

# Silence unused-import lint while keeping a stable import surface.
_ = (find_project_root, os)
