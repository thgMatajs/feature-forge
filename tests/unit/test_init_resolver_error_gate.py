"""Regression — init resolver-error recovery helpers (PR #26 review).

Cobre três findings do review do PR #26:

- M2: ``_drop_unresolvable_cards`` parseia ofensores ANCORADO aos prefixos
  estáveis das mensagens do resolver (DEP-MISSING / CONFLICT-*), em vez de
  varrer qualquer texto entre colchetes. Mensagem com wording desconhecido
  (ou colchetes não relacionados) não pode podar cards por engano.
- M3: a poda pode esvaziar o conjunto; ``_drop_unresolvable_cards`` retorna
  ``[]`` nesse caso — o guard em ``init`` (testado via comportamento da
  helper aqui) impede um ``resolve([])`` silencioso.
- B2: ``_resolver_error_gate`` não declara mais o param morto
  ``selected_names``.

Fonte das mensagens: ``engine/cards/resolver.py``.
"""

from __future__ import annotations

import inspect

from engine.cards.loader import CardManifest
from engine.init import _drop_unresolvable_cards, _resolver_error_gate


def _card(name: str) -> CardManifest:
    return CardManifest(
        name=name,
        version="1.0.0",
        schema_version=1,
        description="stub",
        category="backend",
        maturity="stable",
    )


# ── M2 — parse ancorado a prefixos conhecidos ────────────────────────────────


def test_dep_missing_drops_named_card() -> None:
    cards = [_card("firebase-auth"), _card("ktor-client")]
    errors = [
        "DEP-MISSING: card 'firebase-auth' requires 'persistence-server' but no "
        "active card provides it (and it is not a user-provided capability)."
    ]
    remaining = _drop_unresolvable_cards(cards, errors)
    assert [c.name for c in remaining] == ["ktor-client"]


def test_conflict_singular_drops_bracket_list() -> None:
    cards = [_card("a"), _card("b"), _card("c")]
    errors = [
        "CONFLICT-SINGULAR: capability 'persistence-server' is singular but "
        "provided by multiple cards: ['a', 'b']"
    ]
    remaining = _drop_unresolvable_cards(cards, errors)
    assert [c.name for c in remaining] == ["c"]


def test_conflict_label_drops_card_and_bracket_list() -> None:
    cards = [_card("x"), _card("y"), _card("z")]
    errors = [
        "CONFLICT-LABEL: card 'x' declares conflict with capability "
        "'analytics', also provided by: ['y']"
    ]
    remaining = _drop_unresolvable_cards(cards, errors)
    assert [c.name for c in remaining] == ["z"]


def test_unknown_prefix_does_not_drop_cards() -> None:
    """M2: uma mensagem com prefixo desconhecido (wording drift) que por acaso
    contenha colchetes NÃO pode podar cards — o parse antigo (varredura
    ``\\[...\\]`` global) dropava 'a'/'b' aqui por engano.
    """
    cards = [_card("a"), _card("b")]
    errors = [
        "SOME-FUTURE-WARN: caminho inspecionado ['a', 'b'] não relacionado a "
        "conflito de card."
    ]
    remaining = _drop_unresolvable_cards(cards, errors)
    assert [c.name for c in remaining] == ["a", "b"]


def test_bracket_outside_conflict_marker_not_parsed() -> None:
    """M2: colchetes só são parseados sob CONFLICT-SINGULAR/LABEL. Um
    DEP-MISSING que mencione uma lista entre colchetes não deve podar essa
    lista (só o ``card '<name>'``).
    """
    cards = [_card("core"), _card("a"), _card("b")]
    errors = [
        "DEP-MISSING: card 'core' requires 'x' but candidates ['a', 'b'] were "
        "rejected upstream."
    ]
    remaining = _drop_unresolvable_cards(cards, errors)
    # só 'core' some; 'a'/'b' não são ofensores neste marcador
    assert [c.name for c in remaining] == ["a", "b"]


# ── M3 — poda pode esvaziar; helper devolve [] (guard em init usa isto) ───────


def test_drop_can_return_empty_set() -> None:
    cards = [_card("a"), _card("b")]
    errors = [
        "CONFLICT-SINGULAR: capability 'persistence-server' is singular but "
        "provided by multiple cards: ['a', 'b']"
    ]
    remaining = _drop_unresolvable_cards(cards, errors)
    assert remaining == []  # init deve abortar em vez de resolve([])


# ── B2 — param morto removido ────────────────────────────────────────────────


def test_resolver_error_gate_has_no_selected_names_param() -> None:
    sig = inspect.signature(_resolver_error_gate)
    assert "selected_names" not in sig.parameters
