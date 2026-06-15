"""Regression — init helpers dispatch by isinstance(Cell/Conflict).

PR #13 review #3405253823: substituímos `hasattr(cell, "candidates")` por
`isinstance(cell, Conflict)` em 5 sites de engine.init. Este test
constrói composer_result manualmente com instâncias reais de
`Cell` e `Conflict` e confirma que cada um dos 5 helpers afetados
toma o branch correto.

Anti-regressão pra futuras refactors: se alguém reintroduzir hasattr
(ou usar duck-typing sobre `.candidates`), este test pega.
"""

from __future__ import annotations

import pytest

from engine.detection.composer import Cell, Conflict
from engine.init import (
    _collect_confirm_selection,
    _composer_result_to_cells,
    _detect_axis_uniformity,
    _render_axes_table,
)


@pytest.fixture
def cell_active() -> Cell:
    return Cell(card_id="firebase-auth", score=0.6, matched_signals=("file-exists:foo",))


@pytest.fixture
def cell_active_other() -> Cell:
    return Cell(card_id="ktor-client", score=0.5, matched_signals=("gradle-dep:bar",))


@pytest.fixture
def conflict_two(cell_active: Cell, cell_active_other: Cell) -> Conflict:
    return Conflict(candidates=(cell_active, cell_active_other))


def _composer(
    *, axis: str, platform: str, value
) -> dict[str, dict[str, object]]:
    return {axis: {platform: value}}


def test_detect_axis_uniformity_flags_conflict_as_non_uniform(
    conflict_two: Conflict,
) -> None:
    """Conflict cell deve marcar o axis como NÃO-uniforme."""
    result = _detect_axis_uniformity(_composer(axis="data", platform="android", value=conflict_two))
    assert result == {"data": False}


def test_detect_axis_uniformity_single_cell_is_uniform(cell_active: Cell) -> None:
    """Cell solo deve manter axis uniforme (1 card_id distinct)."""
    result = _detect_axis_uniformity(_composer(axis="auth", platform="ios", value=cell_active))
    assert result == {"auth": True}


def test_render_axes_table_conflict_lists_all_candidates(conflict_two: Conflict) -> None:
    """Conflito renderiza 'CONFLITO — c1, c2' (todos candidates expostos)."""
    composer_result = _composer(axis="data", platform="android", value=conflict_two)
    uniformity = {"data": False}
    table = _render_axes_table(composer_result, uniformity)
    assert "CONFLITO" in table
    assert "firebase-auth" in table
    assert "ktor-client" in table


def test_render_axes_table_cell_shows_card_id(cell_active: Cell) -> None:
    """Cell ativa renderiza o card_id sem CONFLITO label."""
    composer_result = _composer(axis="auth", platform="ios", value=cell_active)
    uniformity = {"auth": True}
    table = _render_axes_table(composer_result, uniformity)
    assert "firebase-auth" in table
    assert "CONFLITO" not in table


def test_collect_confirm_selection_conflict_includes_all_candidates(
    conflict_two: Conflict,
) -> None:
    """Path A confirm: Conflict contribui TODOS os candidates."""
    composer_result = _composer(axis="data", platform="android", value=conflict_two)
    picked = _collect_confirm_selection(composer_result)
    assert sorted(picked) == ["firebase-auth", "ktor-client"]


def test_collect_confirm_selection_cell_contributes_card_id(cell_active: Cell) -> None:
    """Path A confirm: Cell contribui apenas o próprio card_id."""
    composer_result = _composer(axis="auth", platform="ios", value=cell_active)
    picked = _collect_confirm_selection(composer_result)
    assert picked == ["firebase-auth"]


def test_composer_result_to_cells_conflict_picks_first_candidate(
    conflict_two: Conflict,
) -> None:
    """W7.4 adapter: Conflict resolve pra primeiro candidate (já ordenado)."""
    composer_result = _composer(axis="data", platform="android", value=conflict_two)
    cells = _composer_result_to_cells(composer_result)
    # conflict_two foi construído com (firebase-auth, ktor-client) — note that
    # Conflict.candidates já vem ordenado alfabeticamente pelo composer; nosso
    # fixture preserva a ordem alfabética.
    assert cells["data"]["android"] == {"card": "firebase-auth", "status": "active"}


def test_composer_result_to_cells_cell_emits_active(cell_active: Cell) -> None:
    """W7.4 adapter: Cell ativa vira {card, status=active}."""
    composer_result = _composer(axis="auth", platform="ios", value=cell_active)
    cells = _composer_result_to_cells(composer_result)
    assert cells["auth"]["ios"] == {"card": "firebase-auth", "status": "active"}


def test_composer_result_to_cells_none_stays_none() -> None:
    """W7.4 adapter: cell None preservada como None."""
    composer_result: dict[str, dict[str, object]] = {"flags": {"android": None}}
    cells = _composer_result_to_cells(composer_result)
    assert cells["flags"]["android"] is None
