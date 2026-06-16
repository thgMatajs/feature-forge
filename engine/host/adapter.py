"""Host adapter abstract interface.

Spec: docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md §2.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class HostName(str, Enum):
    CLAUDE_CODE = "claude-code"
    OPENCODE = "opencode"
    TTY = "tty"
    INTENT_FILE = "intent-file"


class AskKind(str, Enum):
    ASK = "ask"
    ASK_THREE_PATHS = "ask_three_paths"
    ASK_MULTI = "ask_multi"
    ASK_TEXT = "ask_text"


@dataclass(frozen=True)
class AskResult:
    value: str | list[str]
    from_default: bool = False
    paused: bool = False


class PausedForInputError(Exception):
    """Engine sinaliza host pra pausar + emitir pending intent."""


class UserCancelledError(Exception):
    """User abortou via Ctrl+C / 3-caminhos Path C."""


class HostAdapter(ABC):
    name: HostName

    # ``min_selected`` / ``validator_hint`` / ``paths_detail`` são extras
    # de hash + payload espelhando ``engine.ui.question._build_pending``.
    # Default ``None`` preserva backward-compat com callsites pre-0.7a; o
    # delegate de question.py (Task 0.7b) passa esses valores quando os
    # callers nativos os fornecem (ex.: ``ask_text(validator_hint=...)``
    # ou ``ask_multi(min_selected=...)``). Sem isso, hash divergence
    # quebraria intent-id stability (MD-001) e ``pending["command"]``
    # divergiria de HI-002.

    @abstractmethod
    def ask(
        self,
        *,
        kind: AskKind,
        question: str,
        options: dict,
        default: str | None,
        allow_pause: bool,
        min_selected: int | None = None,
        validator_hint: str | None = None,
        paths_detail: list[dict[str, str]] | None = None,
    ) -> AskResult: ...

    @abstractmethod
    def ask_text(
        self,
        *,
        prompt: str,
        default: str | None,
        validator_hint: str | None = None,
    ) -> str: ...

    @abstractmethod
    def ask_multi(
        self,
        *,
        question: str,
        options: dict,
        min: int = 0,
        max: int | None = None,
        min_selected: int | None = None,
    ) -> list[str]: ...

    @abstractmethod
    def emit_progress(self, *, step: str, total: int, current: int) -> None: ...

    @abstractmethod
    def emit_warn(self, *, message: str) -> None: ...
