"""Unit tests for `engine.cards._signal_shapes.parse_gradle_coordinate`.

Helper compartilhado extraído em B-3 (PR #11 master review) — desduplica
shape-validation entre `engine/cards/loader.py` (CARD-020) e
`engine/init._eval_gradle_dep` / `_module_matches_coordinate`. Tests
isolados aqui garantem que regressão no parser seja detectada sem
depender dos call-site tests.
"""

from __future__ import annotations

from engine.cards._signal_shapes import parse_gradle_coordinate


def test_parses_valid_coordinate() -> None:
    """Shape canônica `<group>:<artifact>` retorna tupla parseada."""
    assert parse_gradle_coordinate("io.ktor:ktor-client-core") == (
        "io.ktor",
        "ktor-client-core",
    )


def test_rejects_version_suffix() -> None:
    """`group:artifact:version` tem 2 `:` — não é shape canônica."""
    assert parse_gradle_coordinate("io.ktor:ktor-client-core:2.3.7") is None


def test_rejects_missing_colon() -> None:
    """Sem `:` separator não há shape parseável."""
    assert parse_gradle_coordinate("io.ktor") is None


def test_rejects_empty_artifact() -> None:
    """Lado direito vazio quebra contrato `<group>:<artifact>`."""
    assert parse_gradle_coordinate("io.ktor:") is None


def test_rejects_whitespace() -> None:
    """Qualquer caractere `str.isspace()` é rejeitado (M-001 regression).

    Cobre ASCII space, tab e newline numa única asserção paramétrica
    enxuta — os call-site tests em `test_card_yaml_validation_whitespace.py`
    cobrem cada classe individualmente.
    """
    assert parse_gradle_coordinate("io.ktor: ktor-client-core") is None
    assert parse_gradle_coordinate("io.ktor:\tktor-client-core") is None
    assert parse_gradle_coordinate("io.ktor:ktor-client-core\n") is None


def test_rejects_non_string_or_empty() -> None:
    """`None`, string vazia e tipos não-string viram `None` defensivamente."""
    assert parse_gradle_coordinate(None) is None
    assert parse_gradle_coordinate("") is None
    assert parse_gradle_coordinate(123) is None
    assert parse_gradle_coordinate(["io.ktor", "ktor-client-core"]) is None


def test_rejects_multiple_consecutive_colons() -> None:
    """`io.ktor::ktor-client-core` tem 2 `:` seguidos — não é shape canônica."""
    assert parse_gradle_coordinate("io.ktor::ktor-client-core") is None


def test_rejects_empty_group() -> None:
    """Lado esquerdo vazio quebra contrato `<group>:<artifact>`."""
    assert parse_gradle_coordinate(":ktor-client-core") is None
