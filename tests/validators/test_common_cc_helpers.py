"""Unit tests for cc_threshold_lookup + cc_format_three_paths helpers."""

from __future__ import annotations

import pytest

from _common import (
    DEFAULTS_CC,
    cc_format_three_paths,
    cc_threshold_lookup,
)


def test_lookup_default_when_no_config_and_no_cards() -> None:
    assert cc_threshold_lookup("kotlin", active_cards=[], workflow_config={}) == 10
    assert cc_threshold_lookup("ts", active_cards=[], workflow_config={}) == 15


def test_lookup_workflow_config_overrides_default() -> None:
    cfg = {"cc-gate": {"kotlin": 12, "ts": 20}}
    assert cc_threshold_lookup("kotlin", active_cards=[], workflow_config=cfg) == 12
    assert cc_threshold_lookup("ts", active_cards=[], workflow_config=cfg) == 20
    # Unspecified language falls back to default
    assert cc_threshold_lookup("swift", active_cards=[], workflow_config=cfg) == 10


def test_lookup_card_override_wins_over_workflow_config() -> None:
    cards = [{"cc-gate-override": {"kotlin": {"threshold": 15, "justification": "DSL"}}}]
    cfg = {"cc-gate": {"kotlin": 12}}
    assert cc_threshold_lookup("kotlin", active_cards=cards, workflow_config=cfg) == 15


def test_lookup_multiple_cards_first_wins() -> None:
    cards = [
        {"cc-gate-override": {"kotlin": {"threshold": 15, "justification": "DSL"}}},
        {"cc-gate-override": {"kotlin": {"threshold": 20, "justification": "Other"}}},
    ]
    assert cc_threshold_lookup("kotlin", active_cards=cards, workflow_config={}) == 15


def test_lookup_card_without_threshold_field_falls_through() -> None:
    cards = [{"cc-gate-override": {"kotlin": {"justification": "missing threshold"}}}]
    cfg = {"cc-gate": {"kotlin": 12}}
    assert cc_threshold_lookup("kotlin", active_cards=cards, workflow_config=cfg) == 12


def test_defaults_table_is_canonical() -> None:
    assert DEFAULTS_CC == {"kotlin": 10, "swift": 10, "ts": 15, "python": 10}


def test_format_three_paths_snapshot() -> None:
    rendered = cc_format_three_paths(
        violations=[
            {
                "file": "app/auth/LoginViewModel.kt",
                "line": 42,
                "function": "handleLogin",
                "cc": 14,
                "threshold": 10,
                "status": "modified",
                "cc_before": 9,
                "language": "kotlin",
            }
        ],
        thresholds={"kotlin": 10},
    )
    # Cabeçalho canônico (.claude/rules/disciplines.md §1)
    assert "🛑 Cyclomatic Complexity gate" in rendered
    assert "O que falhou:" in rendered
    assert "Onde:" in rendered
    assert "Por que importa:" in rendered
    assert "Três caminhos pra resolver:" in rendered
    # Conteúdo específico
    assert "handleLogin" in rendered
    assert "cc=14" in rendered
    assert "↑ de cc=9" in rendered
    assert "kotlin=10" in rendered
    # Caminho 2 nome + formato override
    assert "Override-justify" in rendered
    assert "CC-OVERRIDE: <file>:<func> cc=<N> — <razão concreta>" in rendered
    assert "Sem auto-fix aqui — escolha humana." in rendered


def test_format_three_paths_new_function_annotation() -> None:
    rendered = cc_format_three_paths(
        violations=[
            {
                "file": "app/A.kt",
                "line": 1,
                "function": "novaFunc",
                "cc": 11,
                "threshold": 10,
                "status": "new",
                "cc_before": None,
                "language": "kotlin",
            }
        ],
        thresholds={"kotlin": 10},
    )
    assert "[new]" in rendered
    assert "↑ de cc=" not in rendered
