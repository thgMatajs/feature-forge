"""Slug utilities — leaf util compartilhado (sem deps de engine).

Casa canônica da lógica de slug. Dois derivadores com semânticas distintas
por design:

- ``kebabify`` — token-based (camelCase / runs maiúsculos / números viram
  tokens). Promovido de ``engine/graph/reuse_apply.py`` (era ``_kebabify``)
  pra evitar duplicação quando ``engine.plan`` precisou de infra de slug
  (Mandamento 3). Algoritmo idêntico ao original.
- ``derive_slug`` — char-level NFKD. Front-door do ``forge plan`` (spec §4 C3):
  deriva slug de ticket/frase livre preservando chars isolados e a letra após
  dígito — coisas que o ``kebabify`` token-based descarta. Por isso
  ``derive_slug`` NÃO delega o char-mapping a ``kebabify``; o reuso é no nível
  do módulo compartilhado (mesma casa), não numa chamada forçada.
"""

from __future__ import annotations

import re
import unicodedata as _unicodedata

# Token-based: nomes camelCase, runs maiúsculos, e números viram tokens.
_KEBAB_PARTS = re.compile(r"[A-Za-z][a-z0-9]+|[A-Z]+(?![a-z])|\d+")


def kebabify(text: str) -> str:
    """Kebab-case token-based (mesmo algoritmo do ex-``_kebabify``)."""
    matches = _KEBAB_PARTS.findall(text or "")
    return "-".join(m.lower() for m in matches if m).strip("-")


def derive_slug(text: str) -> str:
    """Deriva slug kebab-case determinístico de ticket/frase livre.

    Regras (spec §4 C3): NFKD strip de acentos · lowercase · não-alfanum →
    hífen · colapsa hífens · trunca pra 3..50 chars · garante início com letra
    (prefixa ``f-`` quando começa com dígito). Char-level por design — preserva
    chars isolados e a letra após dígito, ao contrário do ``kebabify``
    token-based deste mesmo módulo (ver docstring do módulo). Levanta
    ``ValueError`` quando nada derivável (string vazia ou só pontuação).

    Invariante: pra qualquer input que não levante ``ValueError``, o slug
    devolvido SEMPRE satisfaz ``engine.plan._SLUG_PATTERN``
    (``^[a-z][a-z0-9-]{1,48}[a-z0-9]$`` — piso de 3 chars). Por isso o pad
    abaixo é ``< 3`` e não ``< 2``: um piso de 2 escaparia o validador e o
    front-door (``_elicit_slug``) recusaria o próprio default derivado.
    """
    normalized = _unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    out_chars: list[str] = [ch if ch.isalnum() else "-" for ch in ascii_text]
    collapsed = "-".join(filter(None, "".join(out_chars).split("-")))
    if not collapsed:
        raise ValueError(
            f"não consegui derivar um slug de {text!r} — só caracteres inválidos."
        )
    if not collapsed[0].isalpha():
        collapsed = f"f-{collapsed}"
    collapsed = collapsed[:50].rstrip("-")
    # Piso 3 (não 2): casa _SLUG_PATTERN (1 âncora + ≥1 meio + 1 âncora). Um
    # piso de 2 deixaria "ab" escapar como slug que _is_valid_slug recusa.
    if len(collapsed) < 3:
        collapsed = f"{collapsed}-x"[:50]
    return collapsed
