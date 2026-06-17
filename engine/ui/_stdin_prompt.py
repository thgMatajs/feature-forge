"""Helpers in-process pra leitura de prompt via stdin (caminho TTY humano).

Spec: ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §4
(sequência TTY humano).

Estes helpers foram EXTRAÍDOS do antigo ``engine.ui.tty_bridge`` (Wave 2,
clean break — Mandamento #3 reuso) e adaptados pro contexto in-process do
``TtyAdapter``. A diferença essencial em relação ao bridge subprocess-loop:
o ``tty_bridge`` montava um *response-dict* de wire pra escrever em
``forge-response.json``; aqui o loop retorna direto o VALUE escolhido,
porque o ``TtyAdapter`` lê stdin no mesmo processo do engine — não há
arquivo de estado, não há re-invocação.

O que cada helper faz:

- ``_render_prompt`` — desenha o prompt visível (reusa ``renderer`` +
  ``mentor_calmo`` pra layout canônico; voz mentor calmo, sem emoji
  decorativo fora do header de gate).
- ``_is_pause_token`` — token de pausa (Decision 27). ``_PAUSE_TOKENS`` é
  importado de ``engine.ui.question`` — single source of truth.
- ``_normalise_confirm_value`` — mapeia sim/não → bool (parser lenient,
  espelha ``question.confirm``).
- ``_valid_tokens_for`` / ``_is_valid_token`` — validação por ``kind``
  pra re-prompt messaging.
- ``_build_value`` — converte a linha crua de stdin no value canônico do
  ``kind`` (list pra ask_multi, string pra o resto).
- ``_prompt_loop`` — renderiza, lê stdin em loop até
  ``_MAX_INVALID_ATTEMPTS``, retorna o value escolhido OU um
  ``_PauseRequested`` sentinel quando o usuário digita token de pausa.
- ``_TooManyInvalidAttempts`` — sentinel interno pra excesso de inválidos.

Anti-goals:

- Sem lógica de subcommand. Sem escrita de arquivo de estado.
- Sem rendering bespoke — layout novo entra primeiro em ``renderer`` /
  ``mentor_calmo``, depois este módulo reusa.

Refs:
  - ``engine/host/adapters/tty.py`` (único consumidor)
  - ``engine/ui/question.py`` (``_PAUSE_TOKENS``)
"""
from __future__ import annotations

import sys
from typing import Any

from engine.persona import mentor_calmo
from engine.ui import renderer
from engine.ui.question import _PAUSE_TOKENS


# Limite do loop de re-prompt em tokens inválidos. Três tentativas cobrem
# typos reais sem prender o usuário num loop infinito quando stdin está
# mal-comportado (ex.: lixo redirecionado). Depois disso, cancelamos.
_MAX_INVALID_ATTEMPTS = 3


class _TooManyInvalidAttempts(Exception):
    """Sentinel interno — usuário esgotou ``_MAX_INVALID_ATTEMPTS`` inválidos.

    Só o ``TtyAdapter`` captura, mapeando pra ``UserCancelledError`` (exit
    130) + mensagem canônica de cancelamento.
    """


class _PauseRequested(Exception):
    """Sentinel interno — usuário digitou um token de pausa (Decision 27).

    O ``TtyAdapter`` captura e re-levanta como ``UserPausedError`` (exit
    2 quando ``allow_pause``). Pausa é uma resposta de primeira classe,
    distinta de um value.
    """


# --- Pause / confirm helpers -----------------------------------------------


def _is_pause_token(value: str) -> bool:
    return value.strip().lower() in _PAUSE_TOKENS


def _normalise_confirm_value(raw: str) -> bool | None:
    """Mapeia um token sim/não pra bool. Retorna None quando irreconhecível.

    Espelha o parser lenient de ``engine.ui.question.confirm`` pra que a
    leitura aqui aceite os mesmos tokens.
    """
    normalised = raw.strip().lower()
    if normalised in {"s", "sim", "y", "yes", "true"}:
        return True
    if normalised in {"n", "não", "nao", "no", "false"}:
        return False
    return None


# --- Value building ---------------------------------------------------------


def _build_value(intent: dict[str, Any], raw: str) -> Any:
    """Converte a linha crua de stdin no value canônico pra ``kind``.

    In-process: retorna o VALUE diretamente (list pra ask_multi, bool pra
    confirm quando reconhecível, string pro resto). Sem response-dict de
    wire — o ``TtyAdapter`` consome este value direto.
    """
    kind = intent.get("kind", "ask")
    if kind == "ask_multi":
        return [token.strip() for token in raw.split(",") if token.strip()]
    if kind == "confirm":
        normalised = _normalise_confirm_value(raw)
        if normalised is not None:
            return normalised
        return raw  # token desconhecido — validação já barrou antes
    # ask / ask_text / ask_three_paths → string verbatim.
    return raw.strip()


# --- Validation -------------------------------------------------------------


def _valid_tokens_for(intent: dict[str, Any]) -> list[str]:
    """Lista user-facing de tokens válidos pra re-prompt messaging.

    Usado só pro hint "Não entendi — digite [opções válidas]" quando a
    validação falha. Kinds free-text (``ask_text``, ``ask_multi``)
    retornam ``[]`` porque nunca falham validação aqui.
    """
    kind = intent.get("kind", "ask")
    options = intent.get("options") or {}
    if kind == "confirm":
        return ["s", "sim", "n", "não"]
    if kind in {"ask", "ask_three_paths"}:
        return list(options.keys())
    return []


def _is_valid_token(intent: dict[str, Any], raw: str) -> bool:
    """True quando ``raw`` é aceitável pro ``kind`` deste intent.

    Tokens de pausa são sempre válidos (Decision 27). Pra kinds de
    conjunto-fechado (``confirm``, ``ask``, ``ask_three_paths``)
    exigimos match de chave conhecida (ou label exato — cortesia de UX).
    Kinds free-text (``ask_text``, ``ask_multi``) nunca falham aqui.
    """
    if _is_pause_token(raw):
        return True
    kind = intent.get("kind", "ask")
    normalised = raw.strip()
    if not normalised:
        # Linha vazia: válida só quando há default (o caller resolve pro
        # default). Sem default, deixa o caller barrar.
        return intent.get("default") is not None
    if kind == "confirm":
        return _normalise_confirm_value(normalised) is not None
    if kind in {"ask", "ask_three_paths"}:
        options = intent.get("options") or {}
        if normalised in options:
            return True
        # Match de label exato também — cortesia de UX quando o usuário
        # digita o label visível em vez da chave.
        return normalised in {str(label) for label in options.values()}
    # ask_text / ask_multi → sempre aceita.
    return True


def _multi_bounds_error(intent: dict[str, Any], selection: list[str]) -> str | None:
    """Mensagem de re-prompt se a seleção ``ask_multi`` viola min/max.

    Retorna ``None`` quando a seleção está dentro do range (ou quando não
    há bound configurado). Caso contrário devolve uma mensagem mentor-calmo
    explicando o range esperado — o ``_prompt_loop`` re-pergunta em vez de
    aceitar e deixar o ``question.ask_multi`` estourar ``ValueError`` fora.

    O critério espelha o validador outer (``len(result) < min_selected``):
    ``min-count`` carrega o mínimo efetivo (``min_selected`` quando dado,
    senão o ``min`` posicional do ABC) e ``max-count`` o teto opcional.
    """
    count = len(selection)
    min_count = intent.get("min-count") or 0
    max_count = intent.get("max-count")
    if count < min_count:
        return (
            f"Escolha ao menos {min_count} "
            f"{'opção' if min_count == 1 else 'opções'} — "
            f"você marcou {count}."
        )
    if max_count is not None and count > max_count:
        return (
            f"Escolha no máximo {max_count} "
            f"{'opção' if max_count == 1 else 'opções'} — "
            f"você marcou {count}."
        )
    return None


def _resolve_token_to_key(intent: dict[str, Any], raw: str) -> str:
    """Resolve um token cru pra chave de opção (pra ``ask``/``ask_three_paths``).

    Aceita a chave direta OU o label visível e devolve sempre a chave.
    Usado depois de ``_is_valid_token`` já ter aprovado o token.
    """
    normalised = raw.strip()
    options = intent.get("options") or {}
    if normalised in options:
        return normalised
    # Label → chave.
    for key, label in options.items():
        if normalised == str(label):
            return key
    return normalised


# --- Prompt rendering -------------------------------------------------------


def _render_prompt(intent: dict[str, Any]) -> None:
    """Desenha o prompt visível pra um intent.

    Layout segue ``docs/design/07-discipline.md`` (voz mentor calmo, sem
    emoji decorativo fora do header de gate). ``ask_three_paths`` delega
    pra ``mentor_calmo.three_paths_block`` (disciplina §1). Outros kinds
    recebem section_header + question + listagem de opções — o engine já
    formatou ``question`` na voz do projeto, este helper só põe na tela.

    Escreve no ``sys.stderr`` (via ``renderer.write``) pra não poluir o
    ``sys.stdout`` que hosts file-based parseiam — o canal TTY humano usa
    stderr pra UI conversacional, stdout fica pra payload.
    """
    kind = intent.get("kind", "ask")
    question_text = str(intent.get("question", ""))

    if kind == "ask_three_paths":
        paths_detail = intent.get("paths-detail") or []
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
            renderer.write(block, stream=sys.stderr)
            return
        renderer.write(question_text, stream=sys.stderr)
        for key, label in (intent.get("options") or {}).items():
            renderer.write(f"  [{key}] {label}", stream=sys.stderr)
        return

    # ask / ask_text / ask_multi / confirm — mesma forma.
    renderer.write("", stream=sys.stderr)
    renderer.write(
        renderer.section_header(str(intent.get("command", "forge"))),
        stream=sys.stderr,
    )
    renderer.write(question_text, stream=sys.stderr)

    options = intent.get("options") or {}
    if options:
        renderer.write("", stream=sys.stderr)
        for key, label in options.items():
            renderer.write(f"  [{key}] {label}", stream=sys.stderr)

    default = intent.get("default")
    if default is not None:
        renderer.write("", stream=sys.stderr)
        renderer.write(f"(default: {default})", stream=sys.stderr)

    if kind == "ask_multi":
        min_selected = intent.get("min-selected")
        if min_selected:
            renderer.write(
                f"(escolha ao menos {min_selected}, separado por vírgula)",
                stream=sys.stderr,
            )


# --- Prompt loop ------------------------------------------------------------


def _prompt_loop(intent: dict[str, Any]) -> Any:
    """Renderiza o prompt, lê stdin em loop, retorna o value escolhido.

    Re-pergunta até ``_MAX_INVALID_ATTEMPTS`` quando o token não bate com
    o conjunto aceito do kind. Depois do limite, levanta
    ``_TooManyInvalidAttempts``.

    Token de pausa → levanta ``_PauseRequested`` (Decision 27).
    ``EOFError`` (Ctrl+D / stdin fechado) e ``KeyboardInterrupt`` (Ctrl+C)
    propagam pro caller (``TtyAdapter``) que mapeia ambos pra cancel.

    Retorno:
      - ``ask`` / ``ask_three_paths`` → a chave de opção escolhida (str).
      - ``ask_text`` → a linha digitada (str).
      - ``ask_multi`` → list[str] de tokens.
      - ``confirm`` → bool.
    """
    _render_prompt(intent)
    kind = intent.get("kind", "ask")
    for attempt in range(1, _MAX_INVALID_ATTEMPTS + 1):
        raw = input("> ")
        if _is_pause_token(raw):
            raise _PauseRequested()
        if _is_valid_token(intent, raw):
            normalised = raw.strip()
            if not normalised and intent.get("default") is not None:
                # Linha vazia com default → resolve pro default.
                if kind in {"ask", "ask_three_paths"}:
                    return _resolve_token_to_key(intent, str(intent["default"]))
                return _build_value(intent, str(intent["default"]))
            if kind in {"ask", "ask_three_paths"}:
                return _resolve_token_to_key(intent, raw)
            value = _build_value(intent, raw)
            if kind == "ask_multi" and isinstance(value, list):
                # Bound min/max é validado AQUI (não em _is_valid_token, que
                # roda por-token): o critério é sobre a seleção inteira.
                # Fora do range → re-pergunta no mesmo loop em vez de deixar
                # o ValueError do question.ask_multi estourar fora.
                bounds_msg = _multi_bounds_error(intent, value)
                if bounds_msg is not None:
                    renderer.write(
                        f"{bounds_msg} (tentativa {attempt}/{_MAX_INVALID_ATTEMPTS})",
                        stream=sys.stderr,
                    )
                    continue
            return value
        valid = _valid_tokens_for(intent)
        hint = ", ".join(valid) if valid else "uma resposta válida"
        renderer.write(
            f"Não entendi — digite [{hint}]. (tentativa {attempt}/{_MAX_INVALID_ATTEMPTS})",
            stream=sys.stderr,
        )
    raise _TooManyInvalidAttempts()
