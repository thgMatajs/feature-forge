"""Gerador de ``run_id`` pra ``forge qa``.

Formato canonico: ``YYYY-MM-DDTHH-MM-SSZ-<4-char-hex>`` (vide
``docs/schemas/qa-report.md`` linha ~58). UTC garantido por construcao —
se ``now`` chegar com outro fuso, e convertido via ``astimezone``. Sufixo
de 4 caracteres hex provem de ``secrets.token_hex(2)`` (CSPRNG) e
distingue runs paralelas que casaram no segundo.

Consumer canonico: ``engine/qa/ingest.py`` (Phase 0, Task 3.2). API
publica e ``generate_run_id()`` — keyword-only ``now`` pra testes
deterministicos.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


def generate_run_id(*, now: datetime | None = None) -> str:
    """Gera identificador unico de run da forma ``<iso-utc>-<hex4>``.

    Args:
        now: timestamp injetavel pra testes deterministicos. Quando
            ``None`` (default), usa ``datetime.now(timezone.utc)``.
            Quando passado com ``tzinfo`` nao-UTC, e convertido pra UTC
            via ``astimezone`` — a hora local do fuso original NAO
            aparece no resultado.

    Returns:
        String no formato ``YYYY-MM-DDTHH-MM-SSZ-<4-hex>``. Ex:
        ``"2026-06-05T12-30-00Z-a1b2"``. Determinismo so vale pro
        prefixo timestamp; o sufixo e CSPRNG-derived e nunca repete
        previsivelmente.

    Raises:
        TypeError: ``now`` nao e ``datetime`` (defensive — consumer
            pode passar lixo, queremos erro claro nao ``AttributeError``).
    """
    if now is not None and not isinstance(now, datetime):
        raise TypeError(
            f"now deve ser datetime ou None, recebi "
            f"{type(now).__name__!r}."
        )

    ts = now if now is not None else datetime.now(timezone.utc)
    if ts.tzinfo is None or ts.utcoffset().total_seconds() != 0:
        ts = ts.astimezone(timezone.utc)

    formatted = ts.strftime("%Y-%m-%dT%H-%M-%SZ")
    suffix = secrets.token_hex(2)  # 2 bytes => 4 chars hex
    return f"{formatted}-{suffix}"
