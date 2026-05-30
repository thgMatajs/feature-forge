"""Atomic YAML read/write helpers.

Why atomic: feature-forge writes config and memory files concurrently with
hook handlers running. A partial write (process killed mid-flush) would
corrupt the file. We write to `path.tmp` and `os.replace()` it onto the
target, which is atomic on POSIX and Windows for same-filesystem renames.

Backup policy follows `docs/design/07-discipline.md §3`:
- `.bak` sits next to the original, suffix literal.
- 7-day default retention (configurable in workflow-config).
- Never auto-delete; doctor only reports overdue.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class YamlIOError(RuntimeError):
    """Raised when a YAML file cannot be parsed, with file context attached."""


def read_yaml(path: Path) -> Any:
    """Safe-load a YAML file. Returns parsed object (dict/list/scalar).

    Raises YamlIOError with the file path attached on parse failure so
    callers don't have to wrap.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError:
        raise
    except yaml.YAMLError as exc:
        raise YamlIOError(f"failed to parse YAML at {path}: {exc}") from exc


def read_yaml_or_default(path: Path, default: Any) -> Any:
    """Like read_yaml but returns `default` when the file does not exist."""
    if not path.exists():
        return default
    return read_yaml(path)


def write_yaml(
    path: Path,
    data: Any,
    *,
    atomic: bool = True,
    backup: bool = False,
) -> None:
    """Write `data` to `path` as YAML.

    - `atomic=True` (default) writes to `path.tmp` then renames onto the target.
    - `backup=True` copies the existing target to `path.bak` before overwriting
      (no-op if the target does not yet exist). Retention is enforced
      externally — see `docs/design/07-discipline.md §3`.

    YAML style: block (default_flow_style=False), preserved insertion order
    (sort_keys=False), no aliases (avoids surprising anchors on round-trip).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if backup and path.exists():
        backup_file(path)

    serialized = yaml.safe_dump(
        data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=100,
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


def backup_file(path: Path) -> Path | None:
    """Copy `path` to `path.bak`. Returns the .bak Path, or None if no source.

    `.bak` lives next to the original, suffix literal (no pasta separada).
    Retention is the user's responsibility — `forge doctor` reports overdue.
    """
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    return bak


def bak_age_days(bak_path: Path, *, now: datetime | None = None) -> float:
    """Return age of a .bak file in days (float, fractional days OK)."""
    now = now or datetime.now(timezone.utc)
    mtime = datetime.fromtimestamp(bak_path.stat().st_mtime, tz=timezone.utc)
    delta = now - mtime
    return delta.total_seconds() / 86400.0
