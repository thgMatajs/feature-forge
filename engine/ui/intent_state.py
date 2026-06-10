"""State-file I/O for the DRIFT-1 intent protocol.

Single chokepoint for ``.claude/state/forge-pending.json`` and
``.claude/state/forge-response.json``. Engine reads/writes go through
this module; ``question.py`` stays thin (sentinel + dispatch). The
``tty_bridge`` (W3) also lands here for the read-pending +
write-response half of the loop.

Why a dedicated module:

- Keeps ``question.py`` focused on the API surface preserved for the
  125 callsites across 10 engine modules.
- Atomic write (via ``engine.utils.json_io.write_json``) is a hard
  contract — no caller may bypass it and write directly.
- Race detection has nuance (stale > 10min, recent = error, malformed
  = treat as stale) that lives best next to the writer.

Surface delivered in W1.T3 (foundation):

- ``write_pending(intent, project_root)`` — atomic emit
- ``read_response(project_root, intent_id)`` — None if absent, dict if
  match, raises ``IntentMismatchError`` on intent-id divergence
- ``clear_intent_files(project_root)`` — idempotent cleanup of both
- ``detect_race(project_root, new_intent_id)`` — returns None if free
  to write, sweeps stale pending (> 10min), raises
  ``RaceDetectedError`` if a recent pending with a different intent-id
  is still parked

Companion helpers added in W3 (caller-side of the loop, consumed by
``engine.ui.tty_bridge``):

- ``read_pending(project_root)`` — None if absent, dict otherwise.
  Counterpart to ``read_response`` from the bridge's perspective.
- ``write_response(project_root, response)`` — atomic emit using the
  same tempfile-rename strategy.

Refs:
- ``docs/superpowers/specs/drift-1-intent-protocol.md`` §2, §3, §9
- ``docs/schemas/intent-protocol.md``
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.utils import json_io
from engine.utils.paths import claude_dir

# Pending older than this is considered orphaned and gets swept.
_STALE_THRESHOLD_SECONDS = 10 * 60  # 10 minutes


class IntentMismatchError(RuntimeError):
    """Raised when a response file's intent-id does not match the caller's.

    Forensic by design: the file is preserved for inspection rather than
    silently discarded. Top-level handler maps this to exit code 1.
    """


class RaceDetectedError(RuntimeError):
    """Raised when a recent pending intent (≤ 10min) blocks a new one.

    The existing pending is NOT overwritten. Caller must wait or delete
    ``.claude/state/forge-pending.json`` by hand. Top-level handler maps
    this to exit code 1 with the mentor-calmo phrasing carried in
    ``args[0]``.
    """


# --- Path helpers ----------------------------------------------------------


def _state_dir(project_root: Path) -> Path:
    """``.claude/state/`` for this project. Promoted to ``engine.utils.paths``
    when a second consumer appears (anti-procrastination would say now,
    but the spec already flagged this as a deferred promotion).
    """
    return claude_dir(project_root) / "state"


def _pending_path(project_root: Path) -> Path:
    return _state_dir(project_root) / "forge-pending.json"


def _response_path(project_root: Path) -> Path:
    return _state_dir(project_root) / "forge-response.json"


# --- write_pending ---------------------------------------------------------


def write_pending(intent: dict[str, Any], project_root: Path) -> None:
    """Emit the pending intent atomically.

    ``intent`` must already be a fully-formed dict matching
    ``docs/schemas/intent-protocol.md``. Validation of the shape lives
    with the caller (``question.py``); this module trusts its sole
    in-tree consumer.
    """
    json_io.write_json(_pending_path(project_root), intent)


# --- read_pending (W3 companion) -------------------------------------------


def read_pending(project_root: Path) -> dict[str, Any] | None:
    """Read ``.claude/state/forge-pending.json`` if present.

    Mirrors ``read_response`` but for the engine→caller direction: the
    ``tty_bridge`` loop calls this whenever the subprocess exits with
    code 2, to discover what input the engine is asking for.

    Returns:
    - ``None`` when no pending file is on disk. The caller treats this
      as a clean exit-2 path (e.g. CR-003: user paused via response and
      the engine cleared state).
    - The decoded dict otherwise.

    Raises ``json_io.JsonIOError`` (propagated) on a malformed file —
    same contract as ``read_response``. Forensic preservation per SPEC §3
    is the caller's choice; this function does not touch the file.
    """
    path = _pending_path(project_root)
    if not path.exists():
        return None
    return json_io.read_json(path)


# --- write_response (W3 companion) -----------------------------------------


def write_response(project_root: Path, response: dict[str, Any]) -> None:
    """Emit the response payload atomically.

    Counterpart to ``write_pending``: same tempfile-rename strategy via
    ``engine.utils.json_io.write_json``, same trust contract (the caller
    formed a schema-compliant dict). Used by ``tty_bridge`` after the
    user supplies input via stdin; the engine then consumes it through
    ``read_response`` on the next invocation.
    """
    json_io.write_json(_response_path(project_root), response)


# --- read_response ---------------------------------------------------------


def read_response(project_root: Path, intent_id: str) -> dict[str, Any] | None:
    """Read the response file matching ``intent_id``.

    Returns:
    - ``None`` if the response file is absent (caller emits pending).
    - The decoded dict if the response is present and its ``intent-id``
      matches ``intent_id``.

    Raises:
    - ``IntentMismatchError`` if a response is on disk but the
      ``intent-id`` differs. The file is preserved for forensic value.
    - ``json_io.JsonIOError`` (propagated) if the response file is
      malformed JSON.
    """
    path = _response_path(project_root)
    if not path.exists():
        return None

    response = json_io.read_json(path)
    written_id = response.get("intent-id")
    if written_id != intent_id:
        raise IntentMismatchError(
            "response intent-id mismatch — "
            f"expected '{intent_id}', got '{written_id}'. "
            f"File preserved at {path} for inspection."
        )
    return response


# --- clear_intent_files ----------------------------------------------------


def clear_intent_files(project_root: Path) -> None:
    """Delete both ``forge-pending.json`` and ``forge-response.json``.

    Idempotent: no-op when either file is already absent. Called by the
    engine after a successful response consume — keeps state clean
    between pauses (sub-Q **Sb** locked in the spec).
    """
    json_io.delete_if_exists(_pending_path(project_root))
    json_io.delete_if_exists(_response_path(project_root))


# --- detect_race -----------------------------------------------------------


def _parse_created_at(value: str) -> datetime | None:
    """Tolerant ISO-8601 parser. Returns None on malformed input."""
    if not isinstance(value, str):
        return None
    try:
        # Normalise the trailing "Z" (Python's fromisoformat accepted it
        # only from 3.11+, and we have a broader tolerance budget here).
        normalised = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalised)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def detect_race(project_root: Path, new_intent_id: str) -> None:
    """Check whether it is safe to write a new pending for ``new_intent_id``.

    Outcomes:

    - No existing pending → returns ``None`` (safe to proceed).
    - Existing pending has the same ``intent-id`` → returns ``None``
      (treated as a re-emission of the same intent, not a race).
    - Existing pending is stale (``created-at`` > 10 minutes old OR
      missing/malformed) → swept; returns ``None``.
    - Existing pending is recent with a different ``intent-id`` →
      raises ``RaceDetectedError`` with a mentor-calmo message pointing
      at the PID and the file path.

    Lock file via ``fcntl.flock`` is deferred — see the spec
    §"Anti-goals + Considerações futuras".
    """
    pending_path = _pending_path(project_root)
    if not pending_path.exists():
        return None

    try:
        existing = json_io.read_json(pending_path)
    except Exception:
        # Malformed pending — treat as stale and sweep.
        json_io.delete_if_exists(pending_path)
        return None

    existing_id = existing.get("intent-id")
    if existing_id == new_intent_id:
        return None

    created = _parse_created_at(existing.get("created-at", ""))
    now = datetime.now(timezone.utc)

    if created is None:
        # No usable timestamp — treat as orphaned.
        json_io.delete_if_exists(pending_path)
        return None

    age_seconds = (now - created).total_seconds()
    if age_seconds > _STALE_THRESHOLD_SECONDS:
        json_io.delete_if_exists(pending_path)
        return None

    pid = existing.get("pid", "?")
    raise RaceDetectedError(
        "outra invocação do forge ainda está aguardando resposta "
        f"(PID {pid}, intent-id '{existing_id}'). "
        f"Aguarde a conclusão ou remova {pending_path} manualmente "
        "se a sessão anterior abortou sem limpeza."
    )
