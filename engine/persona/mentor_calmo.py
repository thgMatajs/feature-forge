"""Mentor calmo — phrase library and formatters.

All user-facing strings produced by the engine in its own voice (greetings,
acknowledgements, gate violations, progress narration) come from here.

Two flavours of public API:
- Bare phrase functions: `greeting()`, `acknowledgment()`, `pause_message()`.
  Each returns a single rendered string; randomness is local.
- Block formatters: `gate_violation_header()`, `three_paths_block()`,
  `drilldown_question()`. These produce multi-line strings that callers
  hand to `engine/ui/renderer.write()` verbatim.

Randomness is seedable via `set_seed()` so tests can lock the phrase choice
without monkeypatching `random`.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Mapping, Sequence

from engine.utils.paths import lifecycle_root

# H-07: seeded RNG is module-scoped (deterministic-test contract preserved);
# unseeded path returns a fresh `random.Random()` per call to avoid leaking
# state into security-adjacent extensions of this module.
_rng_seeded = random.Random()
_seed: int | None = None


def set_seed(seed: int | None) -> None:
    """Pin the persona's RNG for deterministic tests.

    `seed=None` clears the pin; subsequent calls use a fresh
    `random.Random()` per call (no module-global state).

    A-010 (master review PR #15): **not thread-safe**. `set_seed` and
    `_get_rng` operam sobre `_seed` / `_rng_seeded` module-global sem lock.
    Em testes multi-threaded (pytest-xdist usando threading, não processos)
    duas threads que setam seed em paralelo podem ver `_rng_seeded`
    parcialmente reseedado. Pinning é só para fixtures sequenciais —
    se thread isolation for ambicionada, trocar `_seed`/`_rng_seeded` por
    `threading.local()`. Hoje o projeto não usa threading (xdist roda
    processos), então o risco é teórico.
    """
    global _seed
    _seed = seed
    if seed is not None:
        _rng_seeded.seed(seed)


def _get_rng() -> random.Random:
    """Return seeded RNG when pinned; fresh RNG otherwise."""
    return _rng_seeded if _seed is not None else random.Random()


# ---------------------------------------------------------------------------
# Phrase libraries
# ---------------------------------------------------------------------------

PHRASES_GREETING: tuple[str, ...] = (
    "Pronto. Vamos olhar isso juntos.",
    "Cheguei. Pode me contar o contexto.",
    "Aqui. Vou ler o que já existe antes de propor qualquer coisa.",
    "Tudo bem. Começo lendo o estado atual.",
)

PHRASES_ACK: tuple[str, ...] = (
    "Boa.",
    "Entendi.",
    "Ok.",
    "Tudo bem.",
    "Anotado.",
    "Faz sentido.",
)

PHRASES_BLOCKED: tuple[str, ...] = (
    "Aqui eu não passo sem você decidir.",
    "Esse é um gate que pede escolha humana.",
    "Tenho que parar aqui — você decide o caminho.",
)

PHRASES_PROGRESS_INIT: tuple[str, ...] = (
    "Lendo cards canônicos…",
    "Detectando assinaturas no projeto…",
    "Mapeando a estrutura atual…",
    "Comparando contra os presets disponíveis…",
)

PHRASES_PROGRESS_PLAN: tuple[str, ...] = (
    "Carregando contexto do feature…",
    "Cruzando contracts com a memória de projeto…",
    "Verificando ambiguidades antes de seguir…",
)

PHRASES_PROGRESS_IMPLEMENT: tuple[str, ...] = (
    "Lendo o Task Contract…",
    "Confirmando readiness…",
    "Preparando o plano antes de tocar arquivo…",
)


# ---------------------------------------------------------------------------
# Public phrase API
# ---------------------------------------------------------------------------

def greeting() -> str:
    """Neutral session opener. Never starts with 'olá!' or exclamation.

    Variação intencional pra contextos conversacionais; fluxos
    determinísticos (como `forge init`) usam `greeting_stable()` (P-07).
    """
    return _get_rng().choice(PHRASES_GREETING)


def greeting_stable() -> str:
    """Abertura determinística — usada por fluxos não-conversacionais (init).

    greeting() varia de propósito pra contextos conversacionais; o init é
    um pipeline determinístico e opta por uma abertura estável (P-07).
    """
    return PHRASES_GREETING[0]


def acknowledgment() -> str:
    """Short ack between steps. Used after user input, before the next move."""
    return _get_rng().choice(PHRASES_ACK)


def pause_message(
    slug: str | None = None,
    resume_command: str | None = None,
    project_root: Path | None = None,
) -> str:
    """Pause confirmation per discipline §7.

    Always includes WHERE state was saved and HOW to resume. Never says
    'aborted' here — abort is a different code path (`forge undo`).

    Args:
        slug: feature slug whose state was saved, or None for the generic root.
        resume_command: command string to show for resuming. Defaults to
            "forge {plan|implement|evolve} <slug>".
        project_root: project root used to derive the lifecycle path via
            ``lifecycle_root``. When None, falls back to a relative reference.
    """
    if project_root is not None:
        root = lifecycle_root(project_root)
        # Render as a relative path from project_root so the message is portable.
        try:
            rel = root.relative_to(project_root)
        except ValueError:
            rel = root
        where = f"{rel}/{slug}/status.json" if slug else f"{rel}/"
    else:
        where = (
            f".claude/memory/L1/{slug}/status.json" if slug else ".claude/memory/L1/"
        )
    resume = resume_command or "forge {plan|implement|evolve} <slug>"
    return (
        f"Pausei aqui. Estado salvo em {where}\n"
        f"\n"
        f"Pra retomar: {resume}"
    )


def abort_warning(slug: str) -> str:
    """Confirmation copy for the terminal abort path inside `forge undo`."""
    return (
        f"Marcar '{slug}' como aborted é uma ação terminal.\n"
        f"Os artefatos no docs/ ficam (pra histórico), mas o auto-resume some.\n"
        f"\n"
        f"Tem certeza?"
    )


def progress_phrase(stage: str) -> str:
    """Return a randomly-picked cinematic progress line for a stage.

    Known stages: init, plan, implement. Unknown stage → generic ack.
    """
    if stage == "init":
        return _get_rng().choice(PHRASES_PROGRESS_INIT)
    if stage == "plan":
        return _get_rng().choice(PHRASES_PROGRESS_PLAN)
    if stage == "implement":
        return _get_rng().choice(PHRASES_PROGRESS_IMPLEMENT)
    return acknowledgment()


def drilldown_question(round_number: int) -> str:
    """Drill-down question for an unresolved ambiguity (planning §drill-down).

    Limit is **2 rounds**. After round 2 the agent escalates (rounds 3+ are
    a bug — the caller should call gate_violation_header instead).
    """
    if round_number == 1:
        return (
            "Antes de seguir, me ajuda a entender melhor: "
            "consegue dar um exemplo concreto desse caso?"
        )
    if round_number == 2:
        return (
            "Ainda estou inseguro. Última pergunta antes de escalar: "
            "qual é o comportamento certo do ponto de vista do usuário final?"
        )
    raise ValueError(
        f"drilldown_question accepts rounds 1-2 only (got {round_number}). "
        "Round 3+ should escalate via gate_violation_header."
    )


# ---------------------------------------------------------------------------
# Block formatters
# ---------------------------------------------------------------------------

def gate_violation_header(gate_name: str) -> str:
    """The canonical 🛑 header that opens any gate-violation block.

    Format from discipline §1:

        🛑 {gate-name}

    The body (what failed / where / why) is appended by `three_paths_block`.
    """
    return f"🛑 {gate_name}"


def three_paths_block(
    gate_name: str,
    *,
    what_failed: str,
    where: str,
    why: Sequence[str],
    paths: Sequence[Mapping[str, str]],
) -> str:
    """Render the canonical gate-violation + 3-caminhos block.

    `paths` MUST be exactly 3 entries with keys `label` and `motive`. The
    discipline doc is unambiguous: never 2, never 4 (discipline §1 — "When
    not 3 caminhos genuínos → escalate to abort, never fake a third").

    Layout follows the canonical format in discipline §1 verbatim.
    """
    if len(paths) != 3:
        raise ValueError(
            f"three_paths_block requires exactly 3 caminhos (discipline §1); "
            f"got {len(paths)}"
        )

    why_lines = "\n".join(f"  · {item}" for item in why)
    out: list[str] = [
        gate_violation_header(gate_name),
        "",
        "O que falhou:",
        f"  {what_failed}",
        "",
        "Onde:",
        f"  {where}",
        "",
        "Por que importa:",
        why_lines,
        "",
        "Três caminhos pra resolver:",
        "",
    ]
    for idx, path in enumerate(paths, start=1):
        label = path.get("label", "")
        motive = path.get("motive", "")
        out.append(f"  {idx}) {label}")
        if motive:
            out.append(f"     {motive}")
    out.extend(["", "Sem auto-fix aqui — escolha humana."])
    return "\n".join(out)
