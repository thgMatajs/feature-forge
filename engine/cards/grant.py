"""Decisão sensitive-var grant pra cards em init/reconfigure (QA-11 wave 3).

Quando um card declara `qa-extensions.env-needs` com vars que batem
SENSITIVE_PATTERN, este módulo dispara prompt 3-caminhos pro user:
  1) grant   — adiciona var em workflow-config.qa.sensitive-env-grants
  2) deny    — desativa o card pra esse projeto
  3) abort   — raise UserAbortError (operação cancelada)

Per-projeto (não per-card): se card A grant GITHUB_TOKEN, card B usa
mesmo grant sem novo prompt (KISS, conforme spec §5.3).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from engine.cards.loader import CardManifest
from engine.persona import mentor_calmo


class UserAbortError(RuntimeError):
    """User escolheu path 3 (abort) num prompt sensitive grant."""


@dataclass(frozen=True)
class GrantDecision:
    """Resultado de evaluate_sensitive_grants.

    Attributes
    ----------
    granted : tuple[str, ...]
        Vars aprovadas pelo user neste run (path 1).
    denied_cards : tuple[str, ...]
        Nomes de cards desativados porque user negou pelo menos uma var
        sensitive declarada pelo card (path 2).
    new_grants_to_persist : tuple[str, ...]
        Subconjunto de `granted` que ainda não estava em
        ``workflow_config.qa.sensitive-env-grants`` — caller persiste.
    """

    granted: tuple[str, ...] = ()
    denied_cards: tuple[str, ...] = ()
    new_grants_to_persist: tuple[str, ...] = ()


def evaluate_sensitive_grants(
    cards_to_activate: Iterable[CardManifest],
    workflow_config: dict[str, Any],
) -> GrantDecision:
    """Per card, per sensitive var não-granted, dispara prompt 3-caminhos.

    Dedup cross-cards: mesma var perguntada UMA vez mesmo se N cards
    declaram. Cards com pelo menos 1 var denied entram em ``denied_cards``.

    Parameters
    ----------
    cards_to_activate : Iterable[CardManifest]
        Cards que serão ativados (init) ou re-ativados (reconfigure).
    workflow_config : dict[str, Any]
        Workflow-config carregado; lê ``qa.sensitive-env-grants`` (lista).

    Returns
    -------
    GrantDecision

    Raises
    ------
    UserAbortError
        Se user escolher path 3 em qualquer prompt.
    """
    cards_list = list(cards_to_activate)
    already_granted = _load_existing_grants(workflow_config)

    # Coleta universo de sensitive vars NEW (não-granted), com quais cards
    # as pedem (dedup cross-cards: prompt único por var).
    # deep-019: usa set internamente para dedup quando um mesmo card
    # declara a mesma var duas vezes por engano de yaml (CardManifest
    # apenas tipa como tupla — não dedupliza).
    var_to_cards: dict[str, set[str]] = {}
    for card in cards_list:
        for var in card.sensitive_env_needs:
            if var in already_granted:
                continue
            var_to_cards.setdefault(var, set()).add(card.name)

    granted: list[str] = []
    denied_vars: set[str] = set()

    # Prompt único per var (ordem estável pra UX determinística)
    for var in sorted(var_to_cards):
        cards_requesting = sorted(var_to_cards[var])
        decision = _prompt_sensitive_grant(
            card_name=", ".join(cards_requesting),
            var=var,
        )
        if decision == "grant":
            granted.append(var)
        elif decision == "deny":
            denied_vars.add(var)
        elif decision == "abort":
            raise UserAbortError(
                f"User abortou grant pra var sensitive {var!r} "
                f"(cards pedindo: {cards_requesting})"
            )
        else:
            raise RuntimeError(
                f"_prompt_sensitive_grant retornou decisão inválida: {decision!r}"
            )

    # Cards com pelo menos 1 var denied → denied_cards
    # deep-009: short-circuit quando nenhuma var foi denied — economiza
    # O(N*M) cards × env_needs no caminho comum (re-run sem novos prompts).
    # NB: denied_vars só contém vars denied NESTA sessão; cards que dependem
    # apenas de already_granted não são afetados.
    denied_cards: list[str] = []
    if denied_vars:
        for card in cards_list:
            if any(v in denied_vars for v in card.sensitive_env_needs):
                denied_cards.append(card.name)

    return GrantDecision(
        granted=tuple(granted),
        denied_cards=tuple(denied_cards),
        new_grants_to_persist=tuple(granted),  # já filtrado por already_granted
    )


def _load_existing_grants(workflow_config: dict[str, Any]) -> set[str]:
    """Lê workflow_config.qa.sensitive-env-grants tolerando shape malformado."""
    qa_section = (workflow_config or {}).get("qa") or {}
    raw = qa_section.get("sensitive-env-grants", [])
    if not isinstance(raw, list):
        # Fail-safe: shape ruim vira [] (não raise); warning visível.
        # deep-015: emoji padronizado para '⚠' plain (sem variation
        # selector U+FE0F) para render consistente cross-terminal.
        print(
            f"⚠ qa.sensitive-env-grants tem shape inesperado ({type(raw).__name__}); "
            f"tratando como vazio. Reconcilie via `forge reconfigure → qa`.",
            file=sys.stderr,
        )
        return set()
    return {v for v in raw if isinstance(v, str)}


def _prompt_sensitive_grant(
    *,
    card_name: str,
    var: str,
    prompt_fn: Callable[[str], str] = input,
) -> str:
    """Dispara prompt 3-caminhos mentor-calmo. Retorna 'grant'|'deny'|'abort'.

    Reusa ``mentor_calmo.three_paths_block`` (helper canônico do projeto —
    discipline §1, 3 caminhos exatos).

    deep-017: DI seam via ``prompt_fn`` (default ``input``). Tests injetam
    callable em vez de monkeypatch global, mantendo a fn pura e fácil de
    re-utilizar (futuras variantes TTY-aware com getpass-like).

    deep-004: input não-reconhecido NÃO mais cai em abort silencioso —
    re-prompta até 3x antes de declarar abort, e captura EOFError
    explicitamente pra ambiente não-interativo (CI sem TTY).
    """
    block = mentor_calmo.three_paths_block(
        f"Card pede acesso a variável sensitive: {var}",
        what_failed=(
            f"O card {card_name!r} declarou {var!r} em "
            f"`qa-extensions.env-needs`. Esta var bate o pattern de var "
            f"sensitive (TOKEN/SECRET/PASSWORD/etc.) e exige autorização "
            f"explícita antes de chegar ao subprocess de validators."
        ),
        where=f"forge init/reconfigure → ativação de card {card_name!r}",
        why=[
            "vars sensitive no env do subprocess podem vazar via log/traceback",
            "card extension é trust-on-install — autorização explícita audita o gate",
            "grant fica persistido em workflow-config (revisável a qualquer momento)",
        ],
        paths=[
            {
                "label": "Autorizar (grant)",
                "motive": f"adiciona {var!r} em qa.sensitive-env-grants",
            },
            {
                "label": "Negar (deny)",
                "motive": f"card {card_name!r} é desativado pra esse projeto",
            },
            {
                "label": "Abortar",
                "motive": "operação cancelada; ajuste manual em workflow-config se quiser",
            },
        ],
    )
    print(block, file=sys.stderr)
    for _attempt in range(3):
        try:
            choice = prompt_fn("Escolha [1/2/3]: ").strip()
        except EOFError:
            # Ambiente sem stdin interativo (CI pipeline, forge init
            # automatizado): aborta com mensagem explícita em vez de
            # bubble do EOFError nu.
            print(
                "stdin fechado — abortando grant. Use `forge reconfigure` "
                "interativo para ajustar manualmente.",
                file=sys.stderr,
            )
            return "abort"
        mapped = {"1": "grant", "2": "deny", "3": "abort"}.get(choice)
        if mapped is not None:
            return mapped
        print(
            f"Entrada {choice!r} não reconhecida — esperado 1, 2 ou 3.",
            file=sys.stderr,
        )
    return "abort"  # 3 tentativas inválidas → abort explícito
