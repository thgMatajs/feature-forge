"""WR-01 (Onda 1, fix-forward): na saída cinematográfica por-linha, um validator
``degraded`` (infra off-contract) tem que ser DISTINGUÍVEL de um ``warn``
(código com ressalva).

Antes: ``degraded`` reusava o glyph ``⚠`` do ``warn`` e o bloco de mensagem de
``_render_line`` só disparava pra ``warn`` — então a linha de um degraded ficava
``├ nome  ⚠ 5ms``, idêntica a um warn, SEM o motivo da degradação. O sumário-box
agregado distinguia (``Degraded: N``), mas a linha-a-linha — onde o usuário lê
durante a cascade — apagava justamente a distinção infra-vs-código que é o
coração do H-001.

Fix (Caminho A): glyph próprio pra ``degraded`` + mensagem (o motivo) impressa
na linha. Estes testes capturam o que ``_render_line`` escreve e afirmam que a
linha de degraded difere da de warn em glyph E carrega a mensagem.
"""

from __future__ import annotations

import pytest

from engine import verify
from engine.verify import _render_line, _STATUS_GLYPH, _ValidatorResult


@pytest.fixture
def captured_lines(monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(verify.renderer, "write", lambda s="": lines.append(s))
    return lines


def test_degraded_glyph_differs_from_warn() -> None:
    """O glyph de ``degraded`` é distinto do de ``warn`` no mapa de glyphs."""
    assert _STATUS_GLYPH["degraded"] != _STATUS_GLYPH["warn"], (
        "degraded reusa o glyph do warn — indistinguível na linha (WR-01)"
    )


def test_degraded_line_distinguishable_from_warn_line(captured_lines) -> None:
    """A linha renderizada de um degraded difere da de um warn (glyph) e carrega
    a mensagem (o motivo da degradação)."""
    warn = _ValidatorResult(
        name="some-validator", status="warn", duration_ms=5, message="ressalva de código"
    )
    degraded = _ValidatorResult(
        name="koin", status="degraded", duration_ms=5, message="unrecognized arguments: --scope"
    )

    _render_line(warn)
    _render_line(degraded)

    warn_line, degraded_line = captured_lines[0], captured_lines[1]

    # 1. As linhas não podem ser idênticas em forma (glyph distinto).
    assert warn_line != degraded_line
    # 2. A linha de degraded exibe um glyph que NÃO é o do warn.
    assert _STATUS_GLYPH["warn"] not in degraded_line or _STATUS_GLYPH["degraded"] in degraded_line
    assert _STATUS_GLYPH["degraded"] in degraded_line


def test_degraded_line_prints_degradation_message(captured_lines) -> None:
    """O motivo da degradação (mensagem de stderr/argparse) aparece na linha —
    o usuário lê NA HORA que foi infra off-contract, não só no box agregado."""
    degraded = _ValidatorResult(
        name="koin",
        status="degraded",
        duration_ms=5,
        message="unrecognized arguments: --scope",
    )
    _render_line(degraded)
    line = captured_lines[0]
    assert "unrecognized arguments" in line, (
        "a linha de degraded deve mostrar o motivo (mensagem) — WR-01"
    )


def test_warn_line_still_prints_message(captured_lines) -> None:
    """Guard-rail: o bloco de mensagem do ``warn`` continua funcionando (o fix
    estende pra degraded, não substitui)."""
    warn = _ValidatorResult(
        name="v", status="warn", duration_ms=5, message="ressalva importante"
    )
    _render_line(warn)
    assert "ressalva importante" in captured_lines[0]
