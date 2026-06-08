"""Tests pro modulo engine.qa._common (helpers compartilhados, CONF-004 M-4).

Cobre o contrato basico do helper de timestamp UTC ISO-Z. Tests sao
intencionalmente minimos — o helper e wrapper de 1 linha sobre stdlib.
Vale ter teste pra fixar o formato exato (Z-suffixed, sem offset) caso
alguem refactore pra ``isoformat()`` (que produz ``+00:00``).
"""

from __future__ import annotations

import re

from engine.qa._common import utc_iso_z


_ISO_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_utc_iso_z_returns_z_suffixed_string() -> None:
    """Formato YYYY-MM-DDTHH:MM:SSZ — sufixo literal Z, sem offset."""
    out = utc_iso_z()
    assert _ISO_Z_RE.match(out), f"Formato invalido: {out!r}"


def test_utc_iso_z_never_uses_plus_offset() -> None:
    """Refactor pra ``isoformat()`` produz ``+00:00`` — pegamos no commit."""
    out = utc_iso_z()
    assert "+" not in out
    assert "00:00" not in out  # bloqueio belt-and-suspenders contra "+00:00"
    assert out.endswith("Z")
