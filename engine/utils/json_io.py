"""Atomic JSON read/write helpers.

Mirrors `engine.utils.yaml_io` for the JSON case used by the intent
protocol (`.claude/state/forge-pending.json` and
`.claude/state/forge-response.json`). Why a separate module:

- JSON and YAML use distinct serializers; one wrapper over both would
  obscure error context and force callers to think about format flags.
- Atomicity is a hard requirement of the intent protocol — no reader
  may ever observe a partial file mid-flush.
- ``json.dumps`` with ``ensure_ascii=False`` preserves the persona's
  Portuguese phrasing on disk (mentor-calmo voice survives the wire).

Atomic-write contract (same as ``yaml_io.write_yaml(atomic=True)``):
write to ``path.tmp`` then ``os.replace()`` it onto the target. This is
atomic on POSIX and Windows for same-filesystem renames. If the rename
raises, the temp file is unlinked so no dangling residue stays behind.

DRIFT-1 W1.T2 — foundation only. ``intent_state.py`` (W1.T3) and
``question.py`` (W2) consume this.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class JsonIOError(RuntimeError):
    """Raised when a JSON file cannot be parsed, with file context attached."""


def read_json(path: Path) -> Any:
    """Parse a JSON file. Returns the decoded object (dict/list/scalar).

    Raises ``FileNotFoundError`` when the file is missing (callers that
    want a soft check should use ``read_json_or_default``).

    Raises ``JsonIOError`` with the file path attached on parse failure
    so callers don't have to wrap.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise JsonIOError(f"failed to parse JSON at {path}: {exc}") from exc


def read_json_or_default(path: Path, default: Any) -> Any:
    """Like ``read_json`` but returns ``default`` when the file is absent."""
    if not path.exists():
        return default
    return read_json(path)


def write_json(
    path: Path,
    data: Any,
    *,
    atomic: bool = True,
    indent: int = 2,
) -> None:
    """Write ``data`` to ``path`` as JSON.

    - ``atomic=True`` (default) writes to ``path.tmp`` then ``os.replace``
      onto the target. The replace is the atomic boundary.
    - ``indent=2`` (default) makes the file human-readable on disk; the
      intent protocol files are inspected by humans during debugging.

    JSON style: ``ensure_ascii=False`` so Portuguese characters survive
    readable (no ``\\uXXXX`` escapes), ``sort_keys=False`` so the engine
    can preserve the canonical key order from the spec.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    serialized = json.dumps(
        data,
        indent=indent,
        ensure_ascii=False,
        sort_keys=False,
    )

    if not atomic:
        with path.open("w", encoding="utf-8") as fh:
            fh.write(serialized)
        return

    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        # Defensive: if rename failed, leave no dangling .tmp.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def delete_if_exists(path: Path) -> bool:
    """Delete ``path`` if it exists. Idempotent.

    Returns True when the file was deleted, False when it was already
    absent. Never raises ``FileNotFoundError``.
    """
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
