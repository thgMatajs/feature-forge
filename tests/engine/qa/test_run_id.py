"""Tests for engine.qa.run_id — run identifier generator.

Cobre 3 casos canonicos (TDD):
- formato regex `^\\d{4}-\\d{2}-\\d{2}T\\d{2}-\\d{2}-\\d{2}Z-[0-9a-f]{4}$`
- unicidade do sufixo em rajada de 100 chamadas com mesma timestamp
- UTC enforcement quando ``now`` vem com tz nao-UTC
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from engine.qa.run_id import generate_run_id


RUN_ID_REGEX = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[0-9a-f]{4}$"
)


def test_run_id_format_matches_regex() -> None:
    """Output canonico: ISO-like UTC com dashes + sufixo 4-hex."""
    run_id = generate_run_id()
    assert RUN_ID_REGEX.match(run_id), (
        f"run_id {run_id!r} nao casa com regex canonico"
    )


def test_run_id_suffix_uniqueness() -> None:
    """100 geracoes com a MESMA timestamp injetada produzem sufixos
    com alta entropia (>= 95 distintos). Margem statistical: 4-hex
    = 65536 combinacoes, colisoes em 100 amostras sao raras mas
    possiveis — 95 como floor pra evitar flake."""
    fixed_now = datetime(2026, 6, 5, 12, 0, 0, tzinfo=timezone.utc)
    ids = [generate_run_id(now=fixed_now) for _ in range(100)]
    suffixes = [run_id.split("-")[-1] for run_id in ids]
    distinct = set(suffixes)
    assert len(distinct) >= 95, (
        f"esperava >=95 sufixos distintos em 100 chamadas, "
        f"obtive {len(distinct)} (sufixos: {sorted(distinct)[:5]}...)"
    )


def test_run_id_utc_enforced() -> None:
    """``now`` vem em GMT-3 → run_id reflete o tempo convertido pra UTC,
    nao a hora local do tz original."""
    gmt_minus_3 = timezone(timedelta(hours=-3))
    # 09:30 em GMT-3 == 12:30 UTC
    local_now = datetime(2026, 6, 5, 9, 30, 0, tzinfo=gmt_minus_3)
    run_id = generate_run_id(now=local_now)
    # Prefix antes do sufixo deve ser 12-30 (UTC), nao 09-30 (local)
    prefix = run_id.rsplit("-", 1)[0]
    assert prefix == "2026-06-05T12-30-00Z", (
        f"esperava timestamp em UTC (12-30-00Z), obtive {prefix!r}"
    )
