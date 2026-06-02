"""Smoke tests — docs/schemas/card.md schema annotated.

Garante que o markdown declara o campo aditivo `legacy-marker` introduzido
pela entrega do Gap 5 (Card local overlay). Nenhum runtime check de YAML
real — apenas verifica que o doc lista o campo e a seção de política.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CARD_MD = REPO_ROOT / "docs" / "schemas" / "card.md"


def test_card_md_exists():
    assert CARD_MD.is_file(), f"expected {CARD_MD} to exist"


def test_card_md_documents_legacy_marker():
    text = CARD_MD.read_text(encoding="utf-8")
    # Bloco no schema annotated
    assert "legacy-marker: false" in text, (
        "schema annotated deve incluir o campo `legacy-marker: false` "
        "(default declarado)"
    )
    # Seção de política aditiva
    assert "Optional top-level `legacy-marker`" in text, (
        "doc deve carregar a seção explicativa do campo"
    )
    # Garante que política de schema-version é mencionada
    assert "schema-version` permanece `1`" in text or "schema-version permanece 1" in text


def test_card_md_section_order_preserved():
    """legacy-marker section vem ANTES do schema annotated, não dentro dele."""
    text = CARD_MD.read_text(encoding="utf-8")
    idx_section = text.find("## Optional top-level `legacy-marker`")
    idx_schema = text.find("## The `card.yaml` schema (full annotated)")
    assert idx_section != -1 and idx_schema != -1
    assert idx_section < idx_schema, (
        "seção `legacy-marker` deve ficar ANTES de `## The card.yaml schema`"
    )
