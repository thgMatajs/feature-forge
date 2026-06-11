"""Smoke tests para ``engine.utils.iso.utc_now_iso``.

Garante parity com os 10 helpers legados que substitui (finding #21 do
master review do PR #11). O formato é load-bearing: checkpoints gravados
antes do consolidação têm que continuar legíveis sem migração.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from engine.utils.iso import utc_now_iso


def test_utc_now_iso_returns_zulu_suffix():
    """Sufixo ``Z`` preservado — formato canônico dos checkpoints existentes."""
    ts = utc_now_iso()
    assert ts.endswith("Z")


def test_utc_now_iso_shape_matches_iso8601_seconds_truncated():
    """Bit-a-bit parity: ``YYYY-MM-DDTHH:MM:SSZ`` (20 chars, segundos truncados)."""
    ts = utc_now_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts), (
        f"expected ISO-8601 zulu sem microssegundos, recebi {ts!r}"
    )


def test_utc_now_iso_roundtrip_parses_utc():
    """O timestamp emitido roundtrips via ``datetime.fromisoformat`` (com Z manual)."""
    ts = utc_now_iso()
    # Python 3.11+ aceita Z direto; pra defensividade, normalizamos.
    normalized = ts.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_utc_now_iso_is_close_to_now():
    """Sanity: o timestamp emitido está dentro de 5s do ``now`` real."""
    before = datetime.now(timezone.utc)
    ts = utc_now_iso()
    after = datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    # Truncated to seconds — pode estar até 1s atrás do `before` por truncamento.
    assert (parsed - before).total_seconds() >= -1
    assert (after - parsed).total_seconds() >= -1
