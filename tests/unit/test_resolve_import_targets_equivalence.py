"""Equivalence guard + wildcard/case correction + scale guard para `_resolve_import_targets`.

Fix A (GRAPH-REAL-REPO Stage 1) replaced the correlated `LIKE '%.'||s.name`
subquery with an in-memory `name -> (path, file_id)` index. Para matches LITERAIS
(exato + sufixo `.`+name) o conjunto de edges é idêntico ao algoritmo legado —
este módulo embute a SQL legada como oráculo num fixture de NOMES LIMPOS pra
guardar essa equivalência. Os over-matches acidentais do `LIKE` legado (coringa
`_`/`%` no nome do símbolo; case-insensitivity) são DESCARTADOS por design — o
índice literal é estritamente mais correto — e são guardados diretamente por
`test_resolver_discards_legacy_wildcard_and_case_overmatches` (sem oráculo,
porque o legado casaria esses matches espúrios).
"""

from __future__ import annotations

import time
from pathlib import Path

from engine.graph.builder import (
    _ensure_imports_to_file_id_column,
    _resolve_import_targets,
)
from engine.utils.sqlite_io import open_db, transaction

# Verbatim copy of the legacy resolution query (used ONLY as the test oracle).
_LEGACY_SQL = """
UPDATE imports
SET to_file_id = (
    SELECT s.file_id
    FROM symbols s
    JOIN files f ON s.file_id = f.id
    WHERE s.name = imports.to_symbol
       OR imports.to_symbol LIKE '%.' || s.name
    ORDER BY f.path, s.name
    LIMIT 1
)
WHERE to_file_id IS NULL
"""


def _add_file(conn, path: str) -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language) VALUES (?, 'kotlin')", (path,)
    )
    return cur.lastrowid


def _add_symbol(conn, file_id: int, name: str) -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind) VALUES (?, ?, 'class')",
        (file_id, name),
    )


def _add_import(conn, from_file_id: int, to_symbol: str) -> None:
    conn.execute(
        "INSERT INTO imports(from_file_id, to_symbol, kind, to_file_id) "
        "VALUES (?, ?, 'import', NULL)",
        (from_file_id, to_symbol),
    )


def _snapshot(conn) -> dict[int, int | None]:
    return {
        row["rowid"]: row["to_file_id"]
        for row in conn.execute(
            "SELECT rowid, to_file_id FROM imports"
        ).fetchall()
    }


def _build_fixture(conn) -> None:
    # Fixture de NOMES LIMPOS (sem `_`/`%` no nome, sem divergência de caixa):
    # cobre só os matches literais onde o novo índice e o oráculo legado
    # coincidem. Os casos coringa/case ficam em `_build_wildcard_case_fixture`.
    # Same symbol name "Bar" in three files with deterministic path ordering;
    # ORDER BY f.path must pick "a/Aardvark.kt".
    f_aard = _add_file(conn, "a/Aardvark.kt")
    f_alpha = _add_file(conn, "a/Alpha.kt")
    f_beta = _add_file(conn, "b/Beta.kt")
    f_gamma = _add_file(conn, "c/Gamma.kt")
    consumer = _add_file(conn, "z/Consumer.kt")
    _add_symbol(conn, f_aard, "Bar")
    _add_symbol(conn, f_alpha, "Bar")
    _add_symbol(conn, f_beta, "Bar")
    _add_symbol(conn, f_gamma, "Widget")
    # Suffix match, exact match, no-match, bare-name match.
    _add_import(conn, consumer, "com.x.Bar")     # -> f_aard (min path)
    _add_import(conn, consumer, "Widget")        # -> f_gamma (exact)
    _add_import(conn, consumer, "com.NoSuch")    # -> NULL (unresolved)
    _add_import(conn, consumer, "Bar")           # -> f_aard (min path)


def test_resolver_matches_legacy_on_controlled_fixture(tmp_path: Path) -> None:
    """Equivalência com o oráculo legado para NOMES LIMPOS (matches literais).

    Guard baseline-verde: passa no código atual E após o rewrite. Os casos
    coringa/case (onde o novo índice diverge do legado por design) NÃO entram
    aqui — ver `test_resolver_discards_legacy_wildcard_and_case_overmatches`.
    """
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        # `imports.to_file_id` é migration-only (adicionada por
        # `_ensure_imports_to_file_id_column`, não pelo DDL canônico do
        # `open_db`); replicamos aqui o que `build_full`/incremental fazem
        # pós-`open_db` para o fixture ter a coluna.
        _ensure_imports_to_file_id_column(conn)
        with transaction(conn):
            _build_fixture(conn)
        # 1. Oracle: run the legacy SQL, snapshot, then reset.
        with transaction(conn):
            conn.execute(_LEGACY_SQL)
        oracle = _snapshot(conn)
        with transaction(conn):
            conn.execute("UPDATE imports SET to_file_id = NULL")
        # 2. New algorithm.
        with transaction(conn):
            _resolve_import_targets(conn)
        actual = _snapshot(conn)
        assert actual == oracle
        # Sanity: the fixture actually resolved something and left one NULL.
        assert sum(1 for v in actual.values() if v is None) == 1
        assert sum(1 for v in actual.values() if v is not None) == 3
    finally:
        conn.close()


def _build_wildcard_case_fixture(conn) -> None:
    # Nomes que o `LIKE` legado casaria por coringa/caixa mas que o índice
    # literal (estritamente mais correto) descarta de propósito.
    f_onclick = _add_file(conn, "u/OnClick.kt")
    f_bar = _add_file(conn, "v/Bar.kt")
    consumer = _add_file(conn, "z/Consumer.kt")
    _add_symbol(conn, f_onclick, "on_click")  # `_` vira coringa no LIKE legado
    _add_symbol(conn, f_bar, "bar")           # minúsculo; LIKE é case-insensitive
    # (1) match literal legítimo por sufixo — DEVE resolver.
    _add_import(conn, consumer, "com.x.on_click")   # -> f_onclick
    # (2) match acidental de coringa do LIKE legado — NÃO deve resolver.
    _add_import(conn, consumer, "com.x.onXclick")   # legado casaria via `_`; agora NULL
    # (3) variação de caixa — NÃO deve resolver (índice é case-sensitive).
    _add_import(conn, consumer, "com.x.BAR")        # legado casaria `bar` via LIKE; agora NULL


def test_resolver_discards_legacy_wildcard_and_case_overmatches(
    tmp_path: Path,
) -> None:
    """Correção intencional do artefato coringa/case do `LIKE` legado — NÃO regressão.

    O SQL legado concatenava `s.name` no lado-padrão de `LIKE '%.' || s.name`,
    então `_`/`%` no nome do símbolo agiam como coringa; e o `LIKE` é
    case-insensitive. O índice literal é estritamente mais correto: um import
    `com.x.onXclick` não deve resolver pro símbolo `on_click`, nem `com.x.BAR`
    pro símbolo `bar`. Este teste afirma o comportamento NOVO (corrigido)
    diretamente — o oráculo legado casaria esses três, então NÃO comparamos
    contra ele aqui. É red-first: FALHA no código atual, passa após o rewrite.
    """
    db = tmp_path / "wc.db"
    conn = open_db(db, create=True)
    try:
        _ensure_imports_to_file_id_column(conn)
        with transaction(conn):
            _build_wildcard_case_fixture(conn)
        with transaction(conn):
            _resolve_import_targets(conn)
        resolved = {
            row["to_symbol"]: row["to_file_id"]
            for row in conn.execute(
                "SELECT to_symbol, to_file_id FROM imports"
            ).fetchall()
        }
        # Match literal legítimo por sufixo resolve.
        assert resolved["com.x.on_click"] is not None
        # Over-matches espúrios do `LIKE` legado são descartados por design.
        assert resolved["com.x.onXclick"] is None
        assert resolved["com.x.BAR"] is None
    finally:
        conn.close()


def test_resolver_scale_smoke(tmp_path: Path) -> None:
    db = tmp_path / "scale.db"
    conn = open_db(db, create=True)
    n = 3000
    try:
        _ensure_imports_to_file_id_column(conn)
        with transaction(conn):
            consumer = _add_file(conn, "zzz/Consumer.kt")
            for i in range(n):
                fid = _add_file(conn, f"pkg/File{i:05d}.kt")
                _add_symbol(conn, fid, f"Sym{i:05d}")
                _add_import(conn, consumer, f"com.example.Sym{i:05d}")
        started = time.perf_counter()
        with transaction(conn):
            _resolve_import_targets(conn)
        elapsed = time.perf_counter() - started
        resolved = conn.execute(
            "SELECT COUNT(*) AS c FROM imports WHERE to_file_id IS NOT NULL"
        ).fetchone()["c"]
        assert resolved == n
        # Generous bound: the O(n^2) version would blow past this for n=3000.
        assert elapsed < 10.0, f"resolver too slow: {elapsed:.2f}s"
    finally:
        conn.close()
