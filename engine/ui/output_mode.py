"""Global output-mode resolution (A1 TOKEN-BLIND).

One mode per process, resolved once at ``cli.main`` startup and propagated
via a ``contextvars.ContextVar`` so the single chokepoint ``renderer.write``
can consult it without per-callsite flags. Thread-safe by construction —
covers the validator-dispatch path that subprocesses (Decisão de design 1).

Scope (Decisão de design 2 — ENFORCED via allowlist): ``OutputMode.JSON`` is
only ever RESOLVED for read-commands (status/doctor/verify/memory/graph). For
interactive commands (plan/implement/init/reconfigure/evolve/qa/undo/raw) the
mode resolution refuses to return JSON even when ``FORGE_OUTPUT=json`` is set
or a spurious ``--json`` is in argv — it falls through to TTY/PLAIN. This is
structural: relying on interactive handlers to "just not consult JSON mode"
would not stop the global ``renderer.write`` no-op from silently degrading
their cinematic UX. The allowlist removes that failure mode at the source.

Modes:
    TTY    — interactive terminal: Unicode box-drawing + SGR colours.
    PLAIN  — non-TTY (pipe/CI/redirect): strip SGR + degrade box→ASCII.
    JSON   — machine-readable: cinematic UI suppressed; handler emits JSON.

Mirrors the context-var discipline of ``engine.ui.question._cli_command_context``
(set at cli.main, reset in finally).
"""

from __future__ import annotations

import contextvars
import os
import sys
from enum import Enum
from typing import TextIO


class OutputMode(Enum):
    TTY = "tty"
    PLAIN = "plain"
    JSON = "json"


# H-001 / Decisão de design 2 — JSON mode is a READ-COMMAND-ONLY carve-out.
# Only these commands may ever resolve to OutputMode.JSON. Interactive commands
# (plan/implement/init/reconfigure/evolve/qa/undo/raw) intentionally fall through
# to TTY/PLAIN even under FORGE_OUTPUT=json, so the intent protocol and their
# cinematic UX are never degraded by the global renderer.write no-op. Keep this
# set in sync with the read-commands that gained --json (T2-T5 + pre-existing graph).
_JSON_CAPABLE_COMMANDS: frozenset[str] = frozenset(
    {"status", "doctor", "verify", "memory", "graph"}
)


# Default is PLAIN: a write that happens before cli.main sets the mode
# (library/test callers) degrades safely rather than leaking SGR/Unicode.
_output_mode: contextvars.ContextVar[OutputMode] = contextvars.ContextVar(
    "forge_output_mode", default=OutputMode.PLAIN
)


def _json_requested(argv: list[str]) -> bool:
    """True when the ``--json`` meta-flag is present anywhere in argv.

    Decisão 10 revisitada: ``--json`` is a permitted meta-flag for read-commands.
    We detect it positionally without argparse (the engine deliberately avoids
    argparse — Decisão 19/10). The allowlist in ``detect_output_mode`` is what
    restricts the effect to read-commands; this only reports presence.
    """
    return "--json" in argv


def detect_output_mode(
    argv: list[str], *, command: str | None = None, stream: TextIO | None = None
) -> OutputMode:
    """Resolve the process output-mode.

    ``command`` is the dispatched subcommand (``argv[0]`` at ``cli.main``). JSON
    mode is GATED on it: only read-commands in ``_JSON_CAPABLE_COMMANDS`` may
    resolve to JSON. For any other command — or when ``command`` is ``None``
    (bare/library invocation) — ``--json`` and ``FORGE_OUTPUT=json`` are ignored
    for the purpose of JSON resolution and we fall through to TTY/PLAIN. This is
    the structural enforcement of Decisão de design 2 (H-001).

    Precedence (highest first), AFTER the allowlist gate:
        1. ``--json`` meta-flag in argv          → JSON  (read-command only)
        2. ``FORGE_OUTPUT=json`` env             → JSON  (read-command only)
        3. stream.isatty()                       → TTY
        4. otherwise                             → PLAIN

    Unknown ``FORGE_OUTPUT`` values are ignored (fall through to TTY/PLAIN)
    so a typo never silently corrupts output. ``--json`` wins over a tty so a
    human can force machine output for inspection — but only for read-commands.
    """
    stream = stream if stream is not None else sys.stdout
    json_capable = command in _JSON_CAPABLE_COMMANDS
    if json_capable:
        if _json_requested(argv):
            return OutputMode.JSON
        if os.environ.get("FORGE_OUTPUT", "").strip().lower() == "json":
            return OutputMode.JSON
    # Interactive commands (or no command): JSON is never resolved — the
    # cinematic UX and intent protocol stay intact regardless of env/argv.
    if bool(getattr(stream, "isatty", lambda: False)()):
        return OutputMode.TTY
    return OutputMode.PLAIN


def set_output_mode(mode: OutputMode) -> contextvars.Token:
    """Set the process output-mode; returns a token for ``reset_output_mode``."""
    return _output_mode.set(mode)


def get_output_mode() -> OutputMode:
    """Return the current output-mode (PLAIN when never set)."""
    return _output_mode.get()


def reset_output_mode(token: contextvars.Token) -> None:
    """Undo a prior ``set_output_mode`` (call in a ``finally``)."""
    _output_mode.reset(token)


def is_json_mode() -> bool:
    """Convenience predicate read by read-command handlers."""
    return _output_mode.get() is OutputMode.JSON


__all__ = [
    "OutputMode",
    "detect_output_mode",
    "set_output_mode",
    "get_output_mode",
    "reset_output_mode",
    "is_json_mode",
]
