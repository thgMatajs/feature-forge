"""Piso de trivialidade + exclusão de test-source (GRAPH-REUSE-STAGE2 Task 2).

- within-module: grupos com < REUSE_MIN_BODY_TOKENS (5) tokens distintos são
  descartados; >= 5 mantidos.
- cross-module (>=2 módulos): BYPASSA o piso (mantém mesmo com 2 tokens).
- símbolos em paths de teste (src/test, src/androidTest, ...) NÃO entram na
  detecção (within OU cross).
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.duplicates import (
    REUSE_MIN_BODY_TOKENS,
    detect_all_reuse_findings,
)
from engine.utils.sqlite_io import open_db, transaction

# Piso calibrado no precision spike (72% → 98% de precisão em ntok >= 5).
assert REUSE_MIN_BODY_TOKENS == 5


def _file(conn, path: str, module: str, source_set: str | None = "main",
          platform: str = "android") -> int:
    return conn.execute(
        "INSERT INTO files(path, language, module, source_set, platform) "
        "VALUES (?, 'kotlin', ?, ?, ?)",
        (path, module, source_set, platform),
    ).lastrowid


def _sym(conn, file_id: int, *, name: str, body_hash: str, tokens: str,
         line: int, receiver: str | None = None, kind: str = "fun") -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind, signature, line_start, "
        "receiver_type, body_hash, body_tokens, modifiers) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')",
        (file_id, name, kind, f"{name}()", line, receiver, body_hash, tokens),
    )


def _count(conn, category: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS c FROM reuse_findings WHERE category = ?",
        (category,),
    ).fetchone()["c"]


def _names(conn, category: str) -> set[str]:
    return {
        r["symbol_name"]
        for r in conn.execute(
            "SELECT symbol_name FROM reuse_findings WHERE category = ?",
            (category,),
        ).fetchall()
    }


def test_within_module_floor_filters_trivial_keeps_substantial(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _file(conn, "app/src/main/kotlin/A.kt", "app")
            f2 = _file(conn, "app/src/main/kotlin/B.kt", "app")
            # trivial: 4 tokens distintos (< 5) → deve ser filtrado.
            _sym(conn, f1, name="setToken", body_hash="ht",
                 tokens='["a","b","c","d"]', line=10)
            _sym(conn, f2, name="setToken", body_hash="ht",
                 tokens='["a","b","c","d"]', line=20)
            # substantial: 5 tokens distintos (>= 5) → deve ser mantido.
            _sym(conn, f1, name="resize", body_hash="hr",
                 tokens='["a","b","c","d","e"]', line=40)
            _sym(conn, f2, name="resize", body_hash="hr",
                 tokens='["a","b","c","d","e"]', line=50)
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        assert _names(conn, "duplicate-within-module") == {"resize"}
    finally:
        conn.close()


def test_cross_module_bypasses_floor(tmp_path: Path) -> None:
    """Cross-module PURO (dois módulos AMBOS `platform="android"`) com corpo de
    só 2 `body_tokens` distintos: se fosse within-module cairia no piso, mas o
    Q13 cross-module bypassa o piso. Ambos android de propósito — o Q16
    `redundant-platform-specific` (que roda ANTES do Q13 e reivindicaria a
    chave via `claimed_exact`) exige um par common↔android e NÃO dispara aqui,
    então o par sobra pro Q13 e o finding materializa como
    `duplicate-cross-module`, que é o que este teste precisa exercitar.
    """
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _file(conn, "androidApp/src/main/kotlin/State.kt", "androidApp")
            f2 = _file(conn, "feature/src/main/kotlin/State.kt", "feature")
            # top-level fun (receiver NULL), 2 tokens distintos, em 2 módulos
            # distintos AMBOS android → Q16 não casa (exige common+android), Q12
            # não agrupa (módulos diferentes), Q13 cross-module o mantém (bypass).
            _sym(conn, f1, name="resetState", body_hash="hr", tokens='["a","b"]',
                 line=5)
            _sym(conn, f2, name="resetState", body_hash="hr", tokens='["a","b"]',
                 line=5)
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        assert _names(conn, "duplicate-cross-module") == {"resetState"}
    finally:
        conn.close()


def test_test_source_duplicate_not_reported(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            # byte-idêntico, >= 5 tokens, MESMO módulo, mas em src/test/ →
            # source_set NULL (o KMP set não tem `test`), captado por path.
            t1 = _file(conn, "app/src/test/java/FooTest.kt", "app", source_set=None)
            t2 = _file(conn, "app/src/test/java/BarTest.kt", "app", source_set=None)
            _sym(conn, t1, name="tearDown", body_hash="hd",
                 tokens='["a","b","c","d","e","f"]', line=10)
            _sym(conn, t2, name="tearDown", body_hash="hd",
                 tokens='["a","b","c","d","e","f"]', line=20)
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        assert _count(conn, "duplicate-within-module") == 0
    finally:
        conn.close()
