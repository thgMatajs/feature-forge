"""Unit tests for gate_threshold_lookup + format_three_paths_message helpers."""

from __future__ import annotations

import pytest

from _common import (
    DEFAULTS_CC,
    format_three_paths_message,
    gate_threshold_lookup,
)


def test_lookup_default_when_no_config_and_no_cards() -> None:
    assert gate_threshold_lookup("kotlin", active_cards=[], workflow_config={}) == 10
    assert gate_threshold_lookup("ts", active_cards=[], workflow_config={}) == 15


def test_lookup_workflow_config_overrides_default() -> None:
    cfg = {"cc-gate": {"kotlin": 12, "ts": 20}}
    assert gate_threshold_lookup("kotlin", active_cards=[], workflow_config=cfg) == 12
    assert gate_threshold_lookup("ts", active_cards=[], workflow_config=cfg) == 20
    # Unspecified language falls back to default
    assert gate_threshold_lookup("swift", active_cards=[], workflow_config=cfg) == 10


def test_lookup_card_override_wins_over_workflow_config() -> None:
    cards = [{"cc-gate-override": {"kotlin": {"threshold": 15, "justification": "DSL"}}}]
    cfg = {"cc-gate": {"kotlin": 12}}
    assert gate_threshold_lookup("kotlin", active_cards=cards, workflow_config=cfg) == 15


def test_lookup_multiple_cards_first_wins() -> None:
    cards = [
        {"cc-gate-override": {"kotlin": {"threshold": 15, "justification": "DSL"}}},
        {"cc-gate-override": {"kotlin": {"threshold": 20, "justification": "Other"}}},
    ]
    assert gate_threshold_lookup("kotlin", active_cards=cards, workflow_config={}) == 15


def test_lookup_card_without_threshold_field_falls_through() -> None:
    cards = [{"cc-gate-override": {"kotlin": {"justification": "missing threshold"}}}]
    cfg = {"cc-gate": {"kotlin": 12}}
    assert gate_threshold_lookup("kotlin", active_cards=cards, workflow_config=cfg) == 12


def test_defaults_table_is_canonical() -> None:
    assert DEFAULTS_CC == {"kotlin": 10, "swift": 10, "ts": 15, "python": 10}


def test_format_three_paths_snapshot() -> None:
    rendered = format_three_paths_message(
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
    rendered = format_three_paths_message(
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


def test_format_three_paths_empty_violations_raises() -> None:
    """Empty violations list é programming error; falha alto."""
    with pytest.raises(ValueError, match="at least one violation"):
        format_three_paths_message([], {"kotlin": 10})


def test_lookup_unsupported_language_raises() -> None:
    """Language fora do scope do gate vira ValueError, não KeyError raw."""
    with pytest.raises(ValueError, match="not in gate scope"):
        gate_threshold_lookup("rust", [], {})


def test_lookup_threshold_zero_or_negative_passes_through() -> None:
    """Threshold ≤ 0 é semântica degraded; helper repassa raw."""
    assert gate_threshold_lookup("kotlin", [], {"cc-gate": {"kotlin": 0}}) == 0
    assert gate_threshold_lookup("kotlin", [], {"cc-gate": {"kotlin": -5}}) == -5


# ── Parametrization tests (Fix A1 / A2 — GATE-INFRA-1 closing) ───────────────


def test_lookup_accepts_custom_card_override_key() -> None:
    """`card_override_key` kwarg permite reuso por outros gates numéricos."""
    cards = [{"cog-gate-override": {"kotlin": {"threshold": 25}}}]
    assert (
        gate_threshold_lookup(
            "kotlin",
            active_cards=cards,
            workflow_config={},
            card_override_key="cog-gate-override",
            defaults={"kotlin": 15},
        )
        == 25
    )


def test_lookup_accepts_custom_workflow_block_key() -> None:
    """`workflow_block_key` kwarg desacopla helper do CC gate."""
    cfg = {"cog-gate": {"kotlin": 18}}
    assert (
        gate_threshold_lookup(
            "kotlin",
            active_cards=[],
            workflow_config=cfg,
            workflow_block_key="cog-gate",
            defaults={"kotlin": 15},
        )
        == 18
    )


def test_lookup_accepts_custom_defaults() -> None:
    """`defaults` kwarg permite tabela própria por gate."""
    custom = {"kotlin": 25, "ts": 30}
    assert (
        gate_threshold_lookup(
            "kotlin",
            active_cards=[],
            workflow_config={},
            defaults=custom,
        )
        == 25
    )


def test_lookup_kwargs_default_preserves_cc_behavior() -> None:
    """Sem kwargs custom, comportamento idêntico ao CC gate original."""
    cards = [{"cc-gate-override": {"kotlin": {"threshold": 12}}}]
    cfg = {"cc-gate": {"ts": 20}}
    assert gate_threshold_lookup("kotlin", active_cards=cards, workflow_config=cfg) == 12
    assert gate_threshold_lookup("ts", active_cards=[], workflow_config=cfg) == 20


def test_format_three_paths_accepts_custom_gate_title() -> None:
    """`gate_title` kwarg desacopla render do CC gate."""
    rendered = format_three_paths_message(
        violations=[
            {
                "file": "app/X.kt",
                "line": 1,
                "function": "f",
                "cc": 11,
                "threshold": 10,
                "status": "new",
                "cc_before": None,
                "language": "kotlin",
            }
        ],
        thresholds={"kotlin": 10},
        gate_title="🛑 Cognitive Complexity gate",
    )
    assert "🛑 Cognitive Complexity gate" in rendered
    # CC-specific title NÃO deve aparecer quando custom title é passado
    assert "🛑 Cyclomatic Complexity gate" not in rendered


def test_format_three_paths_accepts_custom_why_lines() -> None:
    """`why_lines` kwarg permite vocabulário próprio do gate."""
    rendered = format_three_paths_message(
        violations=[
            {
                "file": "app/X.kt",
                "line": 1,
                "function": "f",
                "cc": 11,
                "threshold": 10,
                "status": "new",
                "cc_before": None,
                "language": "kotlin",
            }
        ],
        thresholds={"kotlin": 10},
        why_lines=["Funções com Cognitive alto criam fricção cognitiva."],
    )
    assert "Funções com Cognitive alto criam fricção cognitiva." in rendered
    # CC-specific why NÃO deve aparecer
    assert "Funções com CC alto" not in rendered


def test_format_three_paths_accepts_custom_override_example() -> None:
    """`override_example` kwarg para gates com prefix próprio."""
    rendered = format_three_paths_message(
        violations=[
            {
                "file": "app/X.kt",
                "line": 1,
                "function": "f",
                "cc": 11,
                "threshold": 10,
                "status": "new",
                "cc_before": None,
                "language": "kotlin",
            }
        ],
        thresholds={"kotlin": 10},
        override_example="COG-OVERRIDE: <file>:<func> cog=<N> — <razão concreta>",
    )
    assert "COG-OVERRIDE: <file>:<func> cog=<N> — <razão concreta>" in rendered
    assert "CC-OVERRIDE: <file>:<func> cc=<N>" not in rendered


def test_format_three_paths_defaults_preserve_cc_behavior() -> None:
    """Sem kwargs custom, snapshot CC gate byte-a-byte preservado."""
    rendered = format_three_paths_message(
        violations=[
            {
                "file": "app/X.kt",
                "line": 1,
                "function": "f",
                "cc": 11,
                "threshold": 10,
                "status": "new",
                "cc_before": None,
                "language": "kotlin",
            }
        ],
        thresholds={"kotlin": 10},
    )
    assert "🛑 Cyclomatic Complexity gate" in rendered
    assert "Funções com CC alto são mais difíceis" in rendered
    assert "CC-OVERRIDE: <file>:<func> cc=<N> — <razão concreta>" in rendered
