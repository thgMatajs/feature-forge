"""Regression — `mask_strings_and_comments` and unterminated quotes.

Pré-fix (codereviewbot 3417876782 + 3417876787, PR #16 wave final):
quando o lexer encontrava ``"...`` ou ``'...`` sem fechamento até
``\\n`` ou EOF, o opening quote ficava unmasked em ``out[i]``. Conteúdo
da linha era mascarado corretamente, mas a quote sozinha podia ser
contabilizada por matchers downstream que contam quotes pareados — e,
pior, o conteúdo APÓS o ``\\n`` (próxima linha) era processado como
código normal, o que está certo apenas se o opening quote também sumir.

Análogo ao tratamento canônico de block comment não-fechado
(`/* ... EOF`) já presente no módulo: mascara conteúdo + opening
delimiter, preserva newlines pra offsets estáveis.
"""

from __future__ import annotations

from engine.graph._body_text import mask_strings_and_comments


def test_double_quote_unterminated_at_newline_masks_opening() -> None:
    """``"unterminated\\nclass X {`` — opening ``"`` vira espaço, ``class X``
    segue legível na próxima linha.
    """
    src = '"unterminated\nclass X {\n'
    out = mask_strings_and_comments(src)
    # Newline preservado pra offsets estáveis.
    assert out.count("\n") == 2
    # Opening quote mascarado.
    assert out[0] == " "
    # Conteúdo da linha 1 todo mascarado (até o \n).
    assert out[1:12] == " " * 11
    # Linha 2 intocada — parser deve enxergar `class X {`.
    assert "class X {" in out


def test_double_quote_unterminated_at_eof_masks_opening() -> None:
    """``String s = "abc`` (sem ``\\n`` final) — opening + conteúdo viram
    espaços; nenhum ``"`` solto sobra pra confundir matchers de quote.
    """
    src = 'String s = "abc'
    out = mask_strings_and_comments(src)
    # `String s = ` permanece intocado.
    assert out.startswith("String s = ")
    # Opening quote (índice 11) e conteúdo até EOF viram espaços.
    assert out[11:] == "    "  # `"`, `a`, `b`, `c` → 4 espaços
    assert '"' not in out


def test_single_quote_unterminated_at_newline_masks_opening() -> None:
    """``char c = 'a\\nclass Y {`` — análogo ao double-quote."""
    src = "char c = 'a\nclass Y {\n"
    out = mask_strings_and_comments(src)
    assert out.count("\n") == 2
    # `char c = ` intocado.
    assert out.startswith("char c = ")
    # Opening `'` (idx 9) + `a` (idx 10) → espaços.
    assert out[9] == " "
    assert out[10] == " "
    # Linha 2 visível.
    assert "class Y {" in out


def test_single_quote_unterminated_at_eof_masks_opening() -> None:
    """``val c = 'x`` sem newline final — opening + conteúdo viram espaços."""
    src = "val c = 'x"
    out = mask_strings_and_comments(src)
    assert out.startswith("val c = ")
    assert out[8:] == "  "  # `'` + `x` → 2 espaços
    assert "'" not in out


def test_well_terminated_double_quote_preserves_delimiters() -> None:
    """Sanidade: quando fecha normalmente, opening + closing quotes
    permanecem (única mudança é o conteúdo entre delimitadores).
    """
    src = 'val s = "hello"\nfun foo() {}\n'
    out = mask_strings_and_comments(src)
    # Quotes preservadas (opening idx 8, closing idx 14).
    assert out[8] == '"'
    assert out[14] == '"'
    # Conteúdo mascarado.
    assert out[9:14] == "     "
    # Linha 2 intocada.
    assert "fun foo() {}" in out


def test_well_terminated_single_quote_preserves_delimiters() -> None:
    """Sanidade pra char literal bem-formado."""
    src = "char c = 'a';\n"
    out = mask_strings_and_comments(src)
    # Quotes preservadas.
    assert out[9] == "'"
    assert out[11] == "'"
    # Conteúdo mascarado.
    assert out[10] == " "
