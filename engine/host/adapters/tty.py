"""TtyAdapter — caminho TTY humano in-process (sem pending.json).

Spec: ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §4
(sequência TTY humano) + success criterion #5.

Por que in-process (vs. ``IntentFileAdapter`` / ``ClaudeCodeAdapter``)
=====================================================================

Os adapters file-based (intent-file) e CC operam em DRIFT-1: emitem um
pending (arquivo ou marker stdout), levantam ``PausedForInputError`` pro
engine sair com exit 2, e o host re-invoca ``forge`` com a resposta em
disco. Esse loop existe porque o host (Claude Code, ou qualquer harness)
é um processo SEPARADO do engine.

O caminho TTY humano não tem essa separação: o usuário está num terminal
real, ``stdin``/``stdout`` são TTYs do mesmo processo do engine. Logo o
``TtyAdapter`` lê stdin DIRETO, single-pass, in-process:

- NÃO escreve ``forge-pending.json`` nem ``forge-response.json``.
- NÃO usa ``intent_state`` nem ``stable_intent_id`` (não há re-entry).
- Levanta ``UserPausedError`` / ``UserCancelledError`` direto quando o
  usuário pausa/cancela — sem round-trip por arquivo.

Isso substitui o antigo ``engine.ui.tty_bridge`` subprocess-loop (clean
break, Wave 2 — projeto pré-produção, sem usuários reais). Os helpers de
prompt foram extraídos pra ``engine.ui._stdin_prompt`` (Mandamento #3
reuso) e adaptados pro retorno in-process do value.

Guard non-TTY
=============

``ask``/``ask_text``/``ask_multi`` checam ``sys.stdin.isatty()`` antes de
ler. Se chamado num contexto non-TTY (pipe, CI, redirect), levantam
``RuntimeError`` — esse adapter só deveria ser resolvido quando
``detect_host`` retornou ``HostName.TTY`` (que já exige ``isatty``). O
guard é defesa em profundidade contra resolução incorreta.

Refs:
  - ``engine/ui/_stdin_prompt.py`` (helpers extraídos)
  - ``engine/host/adapter.py`` (ABC + exceptions)
  - ``engine/ui/question.py`` (delegate ask/ask_multi/ask_text)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from engine.host.adapter import (
    AskKind,
    AskResult,
    HostAdapter,
    HostName,
    UserCancelledError,
    UserPausedError,
)
from engine.ui import _stdin_prompt, renderer


class TtyAdapter(HostAdapter):
    """Adapter in-process pro terminal humano real.

    Construção é barata; guarda só ``project_root`` por simetria com os
    outros adapters (não usa estado em disco). O contrato in-process
    significa que cada chamada lê stdin diretamente e retorna o value —
    sem loop de pending/response.
    """

    name = HostName.TTY

    def __init__(self, *, project_root: Path):
        self.project_root = Path(project_root)

    # ------------------------------------------------------------------
    # ask / ask_text / ask_multi — leitura direta de stdin
    # ------------------------------------------------------------------

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
    ) -> AskResult:
        self._guard_tty()
        intent = self._build_intent(
            kind=kind,
            question=question,
            options=options or {},
            default=default,
            min_selected=min_selected,
            validator_hint=validator_hint,
            paths_detail=paths_detail,
        )
        value = self._run_loop(intent, allow_pause=allow_pause)
        from_default = (
            default is not None and isinstance(value, str) and value == default
        )
        return AskResult(value=value, from_default=from_default, paused=False)

    def ask_text(
        self,
        *,
        prompt: str,
        default: str | None,
        validator_hint: str | None = None,
    ) -> str:
        self._guard_tty()
        intent = self._build_intent(
            kind=AskKind.ASK_TEXT,
            question=prompt,
            options={},
            default=default,
            validator_hint=validator_hint,
        )
        value = self._run_loop(intent, allow_pause=True)
        if value is None or value == "":
            return default or ""
        return str(value)

    def ask_multi(
        self,
        *,
        question: str,
        options: dict,
        min: int = 0,
        max: int | None = None,
        min_selected: int | None = None,
    ) -> list[str]:
        self._guard_tty()
        # Bound efetivo: ``min_selected`` (nome wire-canônico que
        # ``question.ask_multi`` valida) tem precedência; quando ausente,
        # cai pro ``min`` posicional do ABC. Espelha exatamente o critério
        # do validador outer (``len(result) < min_selected``) pra que o
        # re-prompt do TTY recuse o MESMO que estouraria fora do loop.
        effective_min = min_selected if min_selected is not None else min
        intent = self._build_intent(
            kind=AskKind.ASK_MULTI,
            question=question,
            options=options or {},
            default=None,
            min_selected=min_selected,
        )
        intent["min-count"] = effective_min
        if max is not None:
            intent["max-count"] = max
        value = self._run_loop(intent, allow_pause=True)
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [str(value)]

    # ------------------------------------------------------------------
    # emit_progress / emit_warn — TTY tem UI real
    # ------------------------------------------------------------------

    def emit_progress(self, *, step: str, total: int, current: int) -> None:
        # TTY humano tem UI real — surfacar progresso no stderr é útil e
        # não polui o stdout que hosts file-based parseiam. Diferente dos
        # adapters file/CC (que fazem no-op porque o host dono da UI
        # consome progresso pelo próprio canal), aqui o forge É a UI.
        renderer.write(
            f"[{current}/{total}] {step}",
            stream=sys.stderr,
        )

    def emit_warn(self, *, message: str) -> None:
        # Mesmo racional de ``emit_progress``: TTY humano vê warnings
        # direto no stderr. Voz mentor calmo — sem emoji decorativo.
        renderer.write(f"aviso: {message}", stream=sys.stderr)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _guard_tty(self) -> None:
        """Defesa em profundidade — recusa execução em contexto non-TTY.

        ``detect_host`` só retorna ``HostName.TTY`` quando
        ``sys.stdin.isatty()`` já é True, então em produção este guard
        nunca dispara. Mas se algo resolver este adapter num pipe/CI por
        engano, falhamos cedo com uma mensagem clara em vez de bloquear
        num ``input()`` que nunca recebe linha.
        """
        if not sys.stdin.isatty():
            raise RuntimeError(
                "TtyAdapter chamado em non-TTY context. v1.3: piped stdin "
                "interativo e DEPRECATED — use harness agentico (CLAUDECODE=1, "
                "opencode) ou rode em terminal real. Ver "
                "docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md "
                "§3 A.5."
            )

    def _build_intent(
        self,
        *,
        kind: AskKind,
        question: str,
        options: dict,
        default: str | None,
        min_selected: int | None = None,
        validator_hint: str | None = None,
        paths_detail: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Monta o dict in-memory que os helpers de ``_stdin_prompt`` consomem.

        Mesma forma kebab-case que o wire-pending, mas NUNCA vai pra
        disco — é só o veículo pro layout/validação dos helpers. Campos
        opcionais entram só quando não-None, espelhando os outros
        adapters.
        """
        intent: dict[str, Any] = {
            "kind": kind.value,
            "question": question,
            "options": dict(options) if options else {},
            "default": default,
            "command": "forge",
        }
        if min_selected is not None:
            intent["min-selected"] = min_selected
        if validator_hint is not None:
            intent["validator-hint"] = validator_hint
        if paths_detail is not None:
            intent["paths-detail"] = paths_detail
        return intent

    def _run_loop(self, intent: dict[str, Any], *, allow_pause: bool) -> Any:
        """Roda o loop de stdin, mapeando os sentinels pros erros do ABC.

        - ``_PauseRequested`` → ``UserPausedError`` quando ``allow_pause``;
          senão re-levanta como cancel (pausa não permitida vira abort).
        - ``EOFError`` / ``KeyboardInterrupt`` → ``UserCancelledError``
          (Decision 27 — Ctrl+C/Ctrl+D = abort).
        - ``_TooManyInvalidAttempts`` → ``UserCancelledError``.
        """
        try:
            return _stdin_prompt._prompt_loop(intent)
        except _stdin_prompt._PauseRequested:
            if not allow_pause:
                raise UserCancelledError(
                    "pause não permitido neste contexto — tratado como cancel"
                )
            raise UserPausedError("usuário pausou via stdin")
        except (EOFError, KeyboardInterrupt):
            raise UserCancelledError("usuário cancelou (EOF/Ctrl+C)")
        except _stdin_prompt._TooManyInvalidAttempts:
            raise UserCancelledError("entradas inválidas — cancelando")
