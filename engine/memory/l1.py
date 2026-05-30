"""L1 — per-feature memory (.claude/memory/L1/{feature_slug}/).

L1 is the feature logbook: status, history, hypotheses, ambiguities, elicitation,
rationale, sub-agent dispatches. Lives gitignored as WIP; compresses to
`summary.yaml` on feature-done.

This module owns reads/writes for the 8 L1 files (plus archive lifecycle and
the phase_lock primitive). Schemas: see `docs/schemas/memory.md §L1`.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from engine.memory import MemoryError
from engine.utils.paths import ensure_dir, memory_dir, memory_l1_path
from engine.utils.yaml_io import read_yaml, read_yaml_or_default, write_yaml

# ── Constants ────────────────────────────────────────────────────────────────

_STATUS_FILE = "status.json"
_HISTORY_FILE = "history.jsonl"
_HYPOTHESIS_FILE = "hypothesis.yaml"
_AMBIGUITY_FILE = "ambiguity-map.yaml"
_ELICITATION_FILE = "elicitation.yaml"
_RATIONALE_FILE = "rationale-trace.yaml"
_DISPATCH_FILE = "dispatch-log.jsonl"
_VERIFY_FILE = "verify-log.jsonl"
_PHASE_LOCK_FILE = ".phase-lock"  # plain text — current lock id, or absent

_VALID_STATES = {
    "not-started",
    "planning",
    "planned",
    "implementing",
    "verifying",
    "verified",
    "done",
    "deferred",
    "aborted",
    "paused",
}


# ── Dataclass ────────────────────────────────────────────────────────────────


@dataclass
class L1State:
    """Snapshot of `status.json` for a feature.

    `raw` carries any extra fields present on disk (forward compatibility) so a
    write-back round-trip preserves unknown keys.
    """

    feature_slug: str
    status: str
    last_action_at: str
    last_action_kind: str
    phase_lock: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


# ── Internal helpers ─────────────────────────────────────────────────────────


def _utc_now_iso() -> str:
    """ISO 8601 UTC with second precision and trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _l1_dir(project_root: Path, feature_slug: str) -> Path:
    return memory_l1_path(project_root, feature_slug)


def _archived_dir(project_root: Path) -> Path:
    return memory_dir(project_root) / "L1" / "archived"


@contextmanager
def _file_lock(path: Path) -> Iterator[Any]:
    """Lock advisory exclusive sobre `path` retornando o file handle aberto.

    O caller DEVE reusar o `fh` retornado pra qualquer escrita — assim lock e
    write compartilham o mesmo file descriptor, eliminando a janela racey que
    existia entre "lock released no fd #1" e "abre fd #2 pra append".

    POSIX: `fcntl.flock(LOCK_EX)`. Windows: `msvcrt.locking(LK_LOCK, 1)`.
    Plataformas sem suporte caem em no-op (yield do fd sem lock — single-writer
    invariant em status.json é a última linha de defesa).
    """
    ensure_dir(path.parent)
    fh = open(path, "a", encoding="utf-8")
    locked_posix = False
    locked_win = False
    try:
        if sys.platform == "win32":
            try:
                import msvcrt  # type: ignore[import-not-found]

                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    locked_win = True
                except OSError:
                    pass
            except ImportError:
                pass
        else:
            try:
                import fcntl  # type: ignore[import-not-found]

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                locked_posix = True
            except ImportError:
                pass
        yield fh
    finally:
        try:
            if locked_posix:
                import fcntl  # type: ignore[import-not-found]

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            elif locked_win:
                import msvcrt  # type: ignore[import-not-found]

                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        except (ImportError, OSError):
            pass
        fh.close()


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    """Append uma linha JSON. Lock + write no MESMO fd (sem janela racey)."""
    ensure_dir(path.parent)
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with _file_lock(path) as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise MemoryError(
                    f"malformed JSONL at {path}:{lineno}: {exc}"
                ) from exc
    return out


# ── status.json ──────────────────────────────────────────────────────────────


def read_l1_status(feature_slug: str, project_root: Path) -> Optional[L1State]:
    """Return the L1State for a feature, or None when status.json is absent."""
    path = _l1_dir(project_root, feature_slug) / _STATUS_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MemoryError(f"corrupt status.json at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise MemoryError(f"status.json must be a JSON object at {path}")

    return L1State(
        feature_slug=str(data.get("feature-slug", feature_slug)),
        status=str(data.get("state", data.get("status", "not-started"))),
        last_action_at=str(data.get("last-action-at") or data.get("last_action_at") or ""),
        last_action_kind=str(data.get("last-action") or data.get("last_action_kind") or ""),
        phase_lock=data.get("phase-lock") or data.get("phase_lock"),
        raw=data,
    )


def write_l1_status(state: L1State, project_root: Path) -> None:
    """Persist `state` to status.json atomically (write tmp → rename).

    Validates the state enum and required ISO 8601 timestamp. Preserves any
    unknown keys present in `state.raw` for forward compatibility.
    """
    if state.status not in _VALID_STATES:
        raise MemoryError(
            f"invalid status '{state.status}'; must be one of {sorted(_VALID_STATES)}"
        )
    if not state.last_action_at:
        state.last_action_at = _utc_now_iso()

    payload: dict[str, Any] = dict(state.raw) if state.raw else {}
    payload.update(
        {
            "schema-version": payload.get("schema-version", 1),
            "feature-slug": state.feature_slug,
            "state": state.status,
            "last-action": state.last_action_kind,
            "last-action-at": state.last_action_at,
            "phase-lock": state.phase_lock,
        }
    )

    path = _l1_dir(project_root, state.feature_slug) / _STATUS_FILE
    ensure_dir(path.parent)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# ── history.jsonl ────────────────────────────────────────────────────────────


def append_history(
    feature_slug: str,
    project_root: Path,
    event: dict[str, Any],
) -> None:
    """Append an event to `history.jsonl`. Stamps `at` if missing."""
    if not isinstance(event, dict):
        raise MemoryError("history event must be a dict")
    enriched = dict(event)
    enriched.setdefault("at", _utc_now_iso())
    enriched.setdefault("kind", enriched.pop("event", "unspecified"))
    path = _l1_dir(project_root, feature_slug) / _HISTORY_FILE
    _append_jsonl(path, enriched)


def read_history(
    feature_slug: str,
    project_root: Path,
    *,
    tail: int = 0,
) -> list[dict[str, Any]]:
    """Read history.jsonl; `tail=0` returns all, `tail=N` returns last N entries."""
    if tail < 0:
        raise MemoryError("tail must be non-negative")
    path = _l1_dir(project_root, feature_slug) / _HISTORY_FILE
    entries = _read_jsonl(path)
    if tail == 0:
        return entries
    return entries[-tail:]


# ── dispatch-log.jsonl ───────────────────────────────────────────────────────


def write_dispatch_log(
    feature_slug: str,
    project_root: Path,
    entry: dict[str, Any],
) -> None:
    """Append a sub-agent dispatch event to dispatch-log.jsonl."""
    if not isinstance(entry, dict):
        raise MemoryError("dispatch entry must be a dict")
    enriched = dict(entry)
    enriched.setdefault("at", _utc_now_iso())
    path = _l1_dir(project_root, feature_slug) / _DISPATCH_FILE
    _append_jsonl(path, enriched)


# ── hypothesis / ambiguity / elicitation / rationale (YAML files) ────────────


def _write_yaml_file(project_root: Path, slug: str, name: str, data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise MemoryError(f"{name} payload must be a dict")
    write_yaml(_l1_dir(project_root, slug) / name, data, atomic=True, backup=False)


def _read_yaml_file(project_root: Path, slug: str, name: str) -> Optional[dict[str, Any]]:
    path = _l1_dir(project_root, slug) / name
    if not path.exists():
        return None
    data = read_yaml(path)
    if data is None:
        return None
    if not isinstance(data, dict):
        raise MemoryError(f"{name} must contain a YAML mapping at {path}")
    return data


def write_hypothesis(feature_slug: str, project_root: Path, data: dict[str, Any]) -> None:
    _write_yaml_file(project_root, feature_slug, _HYPOTHESIS_FILE, data)


def read_hypothesis(feature_slug: str, project_root: Path) -> Optional[dict[str, Any]]:
    return _read_yaml_file(project_root, feature_slug, _HYPOTHESIS_FILE)


def write_ambiguity_map(feature_slug: str, project_root: Path, data: dict[str, Any]) -> None:
    _write_yaml_file(project_root, feature_slug, _AMBIGUITY_FILE, data)


def read_ambiguity_map(feature_slug: str, project_root: Path) -> Optional[dict[str, Any]]:
    return _read_yaml_file(project_root, feature_slug, _AMBIGUITY_FILE)


def write_elicitation(feature_slug: str, project_root: Path, data: dict[str, Any]) -> None:
    _write_yaml_file(project_root, feature_slug, _ELICITATION_FILE, data)


def read_elicitation(feature_slug: str, project_root: Path) -> Optional[dict[str, Any]]:
    return _read_yaml_file(project_root, feature_slug, _ELICITATION_FILE)


def write_rationale_trace(feature_slug: str, project_root: Path, data: dict[str, Any]) -> None:
    _write_yaml_file(project_root, feature_slug, _RATIONALE_FILE, data)


def read_rationale_trace(feature_slug: str, project_root: Path) -> Optional[dict[str, Any]]:
    return _read_yaml_file(project_root, feature_slug, _RATIONALE_FILE)


# ── archive ──────────────────────────────────────────────────────────────────


def archive_feature(
    feature_slug: str,
    project_root: Path,
    summary: dict[str, Any],
) -> None:
    """Compress L1/{slug}/ into L1/archived/{slug}.summary.yaml and remove WIP dir.

    `summary` is the distilled snapshot the conductor builds — typically the
    final status, the rationale-trace highlights, and any retrospective notes.
    """
    if not isinstance(summary, dict):
        raise MemoryError("archive summary must be a dict")

    src = _l1_dir(project_root, feature_slug)
    if not src.exists():
        raise MemoryError(
            f"cannot archive '{feature_slug}': no L1 directory at {src}"
        )

    archived = ensure_dir(_archived_dir(project_root))
    target = archived / f"{feature_slug}.summary.yaml"

    enriched = dict(summary)
    enriched.setdefault("schema-version", 1)
    enriched.setdefault("feature-slug", feature_slug)
    enriched.setdefault("archived-at", _utc_now_iso())
    write_yaml(target, enriched, atomic=True, backup=False)

    shutil.rmtree(src)


def list_active_features(project_root: Path) -> list[str]:
    """Sorted list of feature slugs with an L1/ subdir (not yet archived)."""
    root = memory_dir(project_root) / "L1"
    if not root.exists():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and p.name != "archived" and not p.name.startswith(".")
    )


def list_archived_features(project_root: Path) -> list[str]:
    """Sorted list of feature slugs with an archived summary."""
    root = _archived_dir(project_root)
    if not root.exists():
        return []
    return sorted(
        p.stem.removesuffix(".summary")
        for p in root.iterdir()
        if p.is_file() and p.name.endswith(".summary.yaml")
    )


# ── phase_lock ───────────────────────────────────────────────────────────────


def acquire_phase_lock(
    feature_slug: str,
    project_root: Path,
    lock_id: str,
) -> bool:
    """Try to set `phase_lock = lock_id` on status.json. Reentrant for same id.

    Returns True on success, False when another lock id is already active.
    Creates a minimal status.json if absent (state `planning` by default).
    """
    if not lock_id:
        raise MemoryError("lock_id must be non-empty")

    state = read_l1_status(feature_slug, project_root)
    if state is None:
        state = L1State(
            feature_slug=feature_slug,
            status="planning",
            last_action_at=_utc_now_iso(),
            last_action_kind="phase-lock-acquired",
            phase_lock=lock_id,
        )
        write_l1_status(state, project_root)
        return True

    if state.phase_lock and state.phase_lock != lock_id:
        return False

    state.phase_lock = lock_id
    state.last_action_kind = "phase-lock-acquired"
    state.last_action_at = _utc_now_iso()
    write_l1_status(state, project_root)
    return True


def release_phase_lock(feature_slug: str, project_root: Path) -> None:
    """Clear `phase_lock` on status.json. No-op if no lock or no status.json."""
    state = read_l1_status(feature_slug, project_root)
    if state is None or state.phase_lock is None:
        return
    state.phase_lock = None
    state.last_action_kind = "phase-lock-released"
    state.last_action_at = _utc_now_iso()
    write_l1_status(state, project_root)


def current_phase_lock(feature_slug: str, project_root: Path) -> Optional[str]:
    """Return current `phase_lock` value (or None when absent / no status)."""
    state = read_l1_status(feature_slug, project_root)
    return state.phase_lock if state else None


# ── verify-log.jsonl (bonus — symmetry with history) ─────────────────────────


_VERIFY_SCOPES = {"task", "feature", "inferred"}
_VERIFY_RESULTS = {"pass", "warn", "degraded", "fail"}


def append_verify_log(
    feature_slug: str,
    project_root: Path,
    entry: dict[str, Any],
) -> None:
    """Append a `forge verify` result line to verify-log.jsonl.

    Validates against MEM-L1-VL-001..005 (docs/schemas/memory.md §L1
    verify-log.jsonl):

    - MEM-L1-VL-001: line must be a JSON-serialisable mapping (caller passes a dict)
    - MEM-L1-VL-002: timestamp must be ISO8601 UTC (auto-stamped if absent)
    - MEM-L1-VL-003: scope must be in {"task", "feature", "inferred"}
    - MEM-L1-VL-004: result must be in {"pass", "warn", "degraded", "fail"}
    - MEM-L1-VL-005: when result == "degraded", warnings must be >= 1

    Raises MemoryError on schema violation. Required keys: schema-version,
    verify-id, at, scope, validators-run, result.
    """
    if not isinstance(entry, dict):
        raise MemoryError("verify entry must be a dict (MEM-L1-VL-001)")

    enriched = dict(entry)
    enriched.setdefault("timestamp", _utc_now_iso())
    enriched.setdefault("schema-version", 1)
    enriched.setdefault("at", enriched.get("timestamp"))

    required = {
        "schema-version",
        "verify-id",
        "at",
        "scope",
        "validators-run",
        "result",
    }
    missing = sorted(required - set(enriched))
    if missing:
        raise MemoryError(
            f"verify-log entry missing required keys: {missing} "
            "(MEM-L1-VL-001)"
        )

    scope = enriched.get("scope")
    if scope not in _VERIFY_SCOPES:
        raise MemoryError(
            f"verify-log scope {scope!r} must be one of {sorted(_VERIFY_SCOPES)} "
            "(MEM-L1-VL-003)"
        )

    result = enriched.get("result")
    if result not in _VERIFY_RESULTS:
        raise MemoryError(
            f"verify-log result {result!r} must be one of {sorted(_VERIFY_RESULTS)} "
            "(MEM-L1-VL-004)"
        )

    if result == "degraded":
        warnings = enriched.get("warnings")
        if not isinstance(warnings, int) or warnings < 1:
            raise MemoryError(
                "verify-log result=='degraded' requires warnings>=1 (MEM-L1-VL-005)"
            )

    _append_jsonl(_l1_dir(project_root, feature_slug) / _VERIFY_FILE, enriched)


# Re-export for callers walking the package interface.
__all__ = [
    "L1State",
    "MemoryError",
    "read_l1_status",
    "write_l1_status",
    "append_history",
    "read_history",
    "write_dispatch_log",
    "write_hypothesis",
    "read_hypothesis",
    "write_ambiguity_map",
    "read_ambiguity_map",
    "write_elicitation",
    "read_elicitation",
    "write_rationale_trace",
    "read_rationale_trace",
    "archive_feature",
    "list_active_features",
    "list_archived_features",
    "acquire_phase_lock",
    "release_phase_lock",
    "current_phase_lock",
    "append_verify_log",
]

# Suppress unused-import lint — `read_yaml_or_default` is reserved for future
# defaults expansion; keep import to signal intent.
_ = read_yaml_or_default
