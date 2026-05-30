"""Interactive prompts — the local AskUserQuestion fallback.

All user input goes through here so:
- Validation is consistent (no free-text acceptance where an enum was offered).
- Non-TTY callers get a clear error instead of hanging on stdin.
- The 3-caminhos pattern (discipline §1) has a dedicated entrypoint that
  enforces "exactly 3 options labeled A/B/C".

Decision 10 (zero flags) means everything that varies between runs is asked
here — keep this module strict.
"""

from __future__ import annotations

import sys
from typing import Callable, Mapping, Sequence, TextIO

from . import renderer


class PromptAbortedError(RuntimeError):
    """Raised when the user types `para` / `quit` at a prompt that allows it."""


class NonInteractiveError(RuntimeError):
    """Raised when a prompt fires on a non-TTY stdin without a default."""


_PAUSE_TOKENS = {"para", "pausa", "quit", "q", "exit"}


def _read_line(prompt: str, *, stream: TextIO | None = None) -> str:
    stream = stream or sys.stdout
    stream.write(prompt)
    stream.flush()
    line = sys.stdin.readline()
    if not line:
        # EOF on stdin — treat as pause-equivalent rather than crash.
        raise PromptAbortedError("stdin closed")
    return line.rstrip("\n").rstrip("\r")


def ask(
    question: str,
    options: Mapping[str, str],
    *,
    default: str | None = None,
    allow_pause: bool = True,
) -> str:
    """Single-select prompt. `options` is `{key: human_label}`.

    Returns the chosen key. Re-prompts until input matches a key (case-insensitive).
    """
    if not options:
        raise ValueError("ask() requires at least one option")
    keys = list(options.keys())
    default_key = default if default in options else None

    renderer.write(question)
    for key, label in options.items():
        marker = " (default)" if key == default_key else ""
        renderer.write(f"  [{key}] {label}{marker}")

    while True:
        # F5: suffix renderizado no prompt para o usuário ver o default antes de digitar.
        suffix = f" [{default_key}]" if default_key else ""
        raw = _read_line(f">{suffix} ").strip()
        if not raw and default_key:
            return default_key
        normalized = raw.lower()
        if allow_pause and normalized in _PAUSE_TOKENS:
            raise PromptAbortedError("user paused")
        for key in keys:
            if normalized == key.lower():
                return key
        renderer.write(
            renderer.colored(
                f"Resposta '{raw}' não está nas opções. Tente de novo.",
                "yellow",
            )
        )


def ask_multi(
    question: str,
    options: Mapping[str, str],
    *,
    min_selected: int = 0,
) -> list[str]:
    """Multi-select prompt. User types comma-separated keys.

    Order in the returned list mirrors `options` insertion order, not user
    input order — keeps downstream output stable.
    """
    if not options:
        raise ValueError("ask_multi() requires at least one option")
    keys = list(options.keys())

    renderer.write(question)
    for key, label in options.items():
        renderer.write(f"  [ ] {key} — {label}")
    renderer.write("(separe múltiplos com vírgula, ex.: a,c)")

    while True:
        raw = _read_line("> ").strip()
        if raw.lower() in _PAUSE_TOKENS:
            raise PromptAbortedError("user paused")
        picked = [token.strip().lower() for token in raw.split(",") if token.strip()]
        normalized = set(picked)
        invalid = [t for t in normalized if t not in {k.lower() for k in keys}]
        if invalid:
            renderer.write(
                renderer.colored(f"Opções inválidas: {', '.join(invalid)}", "yellow")
            )
            continue
        result = [k for k in keys if k.lower() in normalized]
        if len(result) < min_selected:
            renderer.write(
                renderer.colored(
                    f"Selecione pelo menos {min_selected} opção(ões).", "yellow"
                )
            )
            continue
        return result


def ask_text(
    question: str,
    *,
    default: str | None = None,
    validator: Callable[[str], bool] | None = None,
    validator_hint: str | None = None,
) -> str:
    """Free-text prompt with optional validator and default.

    Validator returns True on accept. `validator_hint` is shown if it rejects.
    """
    renderer.write(question)
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = _read_line(f">{suffix} ").rstrip()
        if not raw and default is not None:
            return default
        if not raw:
            renderer.write(renderer.colored("Entrada vazia — tente de novo.", "yellow"))
            continue
        if raw.lower() in _PAUSE_TOKENS:
            raise PromptAbortedError("user paused")
        if validator is None or validator(raw):
            return raw
        renderer.write(
            renderer.colored(
                validator_hint or "Valor inválido. Tente de novo.", "yellow"
            )
        )


def ask_three_paths(
    gate_name: str,
    paths: Sequence[Mapping[str, str]],
) -> str:
    """Render and read a 3-caminhos prompt per discipline §1.

    `paths` MUST have exactly 3 entries, each with at least `label` and
    `motive`. Returns the chosen key ("a", "b", or "c"). The visual block
    itself is rendered by `engine.persona.mentor_calmo.three_paths_block` —
    this function only handles input.
    """
    if len(paths) != 3:
        raise ValueError(
            f"ask_three_paths requires exactly 3 paths (discipline §1); got {len(paths)}"
        )
    options = {
        "a": paths[0]["label"],
        "b": paths[1]["label"],
        "c": paths[2]["label"],
    }
    return ask(
        f"Qual caminho para resolver '{gate_name}'?",
        options,
        allow_pause=True,
    )


def confirm(question: str, *, default: bool = False) -> bool:
    """Yes/no prompt. `default` is used on empty input."""
    default_key = "s" if default else "n"
    choice = ask(
        question,
        {"s": "sim", "n": "não"},
        default=default_key,
        allow_pause=True,
    )
    return choice == "s"
