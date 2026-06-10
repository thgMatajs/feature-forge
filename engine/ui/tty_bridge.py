"""TTY-fallback subprocess loop for the DRIFT-1 intent protocol.

Sub-question **Sc** of ``docs/superpowers/specs/drift-1-intent-protocol.md``:
when the dispatcher (``bin/forge``) is invoked from a real terminal —
no Claude Code host, no pipes, just stdin/stdout TTYs — it execs through
this module instead of calling ``engine.cli`` directly. The bridge then
drives the engine in subprocess mode, intercepts the canonical exit-2
"paused for input" signal, prompts the user via stdin, writes the
response file, and re-invokes the engine until the subprocess exits
with anything other than 2.

What the bridge does (and only this):

1. Run ``python -m <command_module> <argv...>`` as a subprocess with
   ``FORGE_INTERNAL_TTY_BRIDGE=1`` in the environment so the engine can
   log "we are driving this from a TTY fallback" without changing
   behaviour.
2. If the subprocess exits with anything other than 2, propagate that
   return code verbatim (0 = success, 1 = fatal error, 130 = cancelled).
3. If it exits with 2, read ``.claude/state/forge-pending.json``. When
   that file is absent, the engine exited via ``UserPausedError``
   (CR-003 fix from W2 review) after already clearing state — the user
   asked to pause, the engine acknowledged, and there is nothing left
   to prompt. Propagate exit 2 to the caller (``bin/forge`` later
   surfaces it to the OS).
4. With a pending in hand, render the prompt through
   ``engine.ui.renderer`` and ``engine.persona.mentor_calmo``, read a
   line of stdin, and assemble a response dict matching
   ``docs/schemas/intent-protocol.md``. Write it via
   ``engine.ui.intent_state.write_response`` and loop.
5. ``KeyboardInterrupt`` during the prompt → exit 130 + clear the state
   files. Decision 27 maps Ctrl+C to abort-with-pause-state-cleared.

Reuse:

- ``engine.ui.intent_state`` for read/write of the state files (W1/W3
  surface). The bridge never opens those files by hand.
- ``engine.ui.renderer.write`` for visible output — stays consistent
  with everything else the engine prints (Box, divider, colour fallback).
- ``engine.persona.mentor_calmo.three_paths_block`` /
  ``mentor_calmo.acknowledgment`` for canonical phrasing.
- ``engine.ui.question._PAUSE_TOKENS`` for the pause-token set (Decision
  27 invariant — keeping it in one place avoids drift).

Anti-goals:

- No subcommand logic. The bridge never imports an engine command
  module directly; the subprocess is the only execution channel.
- No bespoke prompt rendering. If a new layout is needed, it lands in
  ``renderer`` / ``mentor_calmo`` first, then this module reuses it.

Refs:

- ``docs/superpowers/specs/drift-1-intent-protocol.md`` §6, §7, §8
- ``docs/superpowers/plans/drift-1-intent-protocol.md`` W3.T1
- ``docs/schemas/intent-protocol.md``
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from engine.persona import mentor_calmo
from engine.ui import intent_state, renderer
from engine.ui.question import _PAUSE_TOKENS
from engine.utils.paths import try_find_project_root


# Exit code for "paused awaiting input" — duplicated locally from SPEC §8
# to keep the bridge importable even if engine.cli is not. (cli.main
# already owns the canonical mapping; here we only need to recognise
# the value coming back from the subprocess.)
_EXIT_PAUSED_FOR_INPUT = 2
_EXIT_USER_CANCELLED = 130


def _project_root() -> Path:
    """Resolve the project root that anchors ``.claude/state/*``.

    Mirrors ``engine.ui.question._project_root_for_io``: walk up from
    cwd looking for ``.claude/workflow-config.yaml``, fall back to cwd
    when no marker is found. Identical resolution keeps the bridge and
    the engine talking to the same state directory in every scenario.
    """
    found = try_find_project_root()
    return found if found is not None else Path.cwd()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Prompt rendering ------------------------------------------------------


def _render_prompt(intent: dict[str, Any]) -> None:
    """Render the visible prompt for one pending intent.

    Layout choices follow ``docs/design/07-discipline.md`` voice rules:
    no decorative emoji outside the canonical gate-violation header, no
    corporate phrasing. ``ask_three_paths`` delegates to
    ``mentor_calmo.three_paths_block`` for the canonical layout
    (discipline §1). Other kinds get a thinner section_header + question
    + options listing — the engine already formatted ``question`` in the
    project voice, the bridge just lays it on screen.
    """
    kind = intent.get("kind", "ask")
    question_text = str(intent.get("question", ""))

    if kind == "ask_three_paths":
        paths_detail = intent.get("paths-detail") or []
        # Defensive: the chokepoint always emits 3 entries (HI-001), but
        # we read from disk here — fall back to a minimal block rather
        # than crash if the file is partial.
        if len(paths_detail) == 3:
            block = mentor_calmo.three_paths_block(
                gate_name=question_text,
                what_failed=question_text,
                where=str(intent.get("command", "")),
                why=("Engine pausou aguardando escolha humana.",),
                paths=tuple(
                    {"label": str(p.get("label", "")), "motive": str(p.get("motive", ""))}
                    for p in paths_detail
                ),
            )
            renderer.write(block)
            return
        # Fallback: render question + options as a degraded block.
        renderer.write(question_text)
        for key, label in (intent.get("options") or {}).items():
            renderer.write(f"  [{key}] {label}")
        return

    # ask / ask_text / ask_multi / confirm — all share the same shape.
    renderer.write("")
    renderer.write(renderer.section_header(intent.get("command", "forge")))
    renderer.write(question_text)

    options = intent.get("options") or {}
    if options:
        renderer.write("")
        for key, label in options.items():
            renderer.write(f"  [{key}] {label}")

    default = intent.get("default")
    if default is not None:
        renderer.write("")
        renderer.write(f"(default: {default})")

    if kind == "ask_multi":
        min_selected = intent.get("min-selected")
        if min_selected:
            renderer.write(f"(escolha ao menos {min_selected}, separado por vírgula)")


def _is_pause_token(value: str) -> bool:
    return value.strip().lower() in _PAUSE_TOKENS


def _normalise_confirm_value(raw: str) -> bool | None:
    """Map a typed yes/no token to a bool. Returns None when unrecognised.

    Mirrors the lenient parser in ``engine.ui.question.confirm`` so the
    response we write here lines up with what the engine accepts on the
    next consume.
    """
    normalised = raw.strip().lower()
    if normalised in {"s", "sim", "y", "yes", "true"}:
        return True
    if normalised in {"n", "não", "nao", "no", "false"}:
        return False
    return None


def _build_response_value(intent: dict[str, Any], raw: str) -> Any:
    """Convert the raw stdin line into the canonical response value for ``kind``.

    Errors here are deliberately permissive — invalid shapes get passed
    through verbatim so the engine's chokepoint (which already has full
    forensic-preservation behaviour) is the one source of truth for
    validation. The bridge stays a thin transport.
    """
    kind = intent.get("kind", "ask")
    if kind == "ask_multi":
        return [token.strip() for token in raw.split(",") if token.strip()]
    if kind == "confirm":
        normalised = _normalise_confirm_value(raw)
        if normalised is not None:
            return normalised
        return raw  # let the engine raise on unknown token, preserving state
    # ask / ask_text / ask_three_paths → string verbatim.
    return raw.strip()


def _build_response(intent: dict[str, Any], raw: str) -> dict[str, Any]:
    """Assemble the response dict to write to ``forge-response.json``."""
    intent_id = intent["intent-id"]
    kind = intent.get("kind", "ask")
    base = {
        "schema-version": 1,
        "intent-id": intent_id,
        "kind": kind,
        "answered-at": _now_iso(),
    }
    if _is_pause_token(raw):
        # Decision 27 — pause is a first-class response, not a value.
        base["paused"] = True
        return base
    base["value"] = _build_response_value(intent, raw)
    return base


def _prompt_user_via_stdin(intent: dict[str, Any]) -> dict[str, Any]:
    """Render the prompt, read one line of stdin, build the response dict.

    ``KeyboardInterrupt`` is allowed to propagate so ``main`` can map it
    to exit 130 (Decision 27).
    """
    _render_prompt(intent)
    raw = input("> ")
    return _build_response(intent, raw)


# --- Public entry point ----------------------------------------------------


def main(command_module: str, argv: Sequence[str]) -> int:
    """Drive the engine in subprocess mode with stdin-based prompt fallback.

    Loops until the subprocess exits with anything other than 2, or the
    user cancels via Ctrl+C / a pause token. See the module docstring
    for the full contract.

    Parameters:
    - ``command_module`` — usually ``"engine.cli"``. Kept parametric so
      a future variant of the bridge could target a different entry
      point without touching this function.
    - ``argv`` — the argv to pass to the engine subprocess. The bridge
      does not parse it; whatever the user typed flows through verbatim.

    Returns: the exit code to pass to the OS.
    """
    project_root = _project_root()
    base_env = {**os.environ, "FORGE_INTERNAL_TTY_BRIDGE": "1"}
    cmd_prefix = [sys.executable, "-m", command_module]

    while True:
        result = subprocess.run(
            [*cmd_prefix, *argv],
            env=base_env,
        )
        rc = result.returncode

        if rc != _EXIT_PAUSED_FOR_INPUT:
            return rc

        # exit 2 — distinguish "engine needs input" from
        # "user paused, state already cleared".
        intent = intent_state.read_pending(project_root)
        if intent is None:
            # CR-003: engine cleared state on UserPausedError; nothing
            # left to prompt. Propagate exit 2 verbatim so bin/forge
            # surfaces it to the OS as "paused, re-invoke to resume".
            return _EXIT_PAUSED_FOR_INPUT

        try:
            response = _prompt_user_via_stdin(intent)
        except KeyboardInterrupt:
            # Decision 27 — Ctrl+C is abort-with-state-cleared.
            intent_state.clear_intent_files(project_root)
            return _EXIT_USER_CANCELLED

        intent_state.write_response(project_root, response)


if __name__ == "__main__":  # pragma: no cover — exercised via subprocess
    if len(sys.argv) < 2:
        renderer.write(
            "usage: python -m engine.ui.tty_bridge <command_module> [argv...]"
        )
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2:]))
