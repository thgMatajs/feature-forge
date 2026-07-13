"""Paridade read-side do universo ampliado (GRAPH-REUSE-STAGE2 Task 3).

`find_duplicates_within_module` / `find_duplicates_cross_module` (read-time,
`forge graph`) espelham a detecção build-time: universo ampliado
(top-level fun + composable_fun), piso de trivialidade (within-only) e
exclusão de test-source.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.utils.sqlite_io import open_db, transaction


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


def test_within_read_broadened_floored_and_test_excluded(tmp_path: Path) -> None:
    """RED: read-side hoje exige `receiver_type IS NOT NULL` → top-level e
    composable não aparecem (rows == []). Após o espelhamento: top-level e
    composable com >=5 tokens aparecem; o trivial (<5) é filtrado pelo piso;
    o dup em src/test/ é excluído.
    """
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _file(conn, "app/src/main/kotlin/A.kt", "app")
            f2 = _file(conn, "app/src/main/kotlin/B.kt", "app")
            # top-level fun, >= 5 tokens → mantido.
            _sym(conn, f1, name="setupToolbar", body_hash="ht",
                 tokens='["a","b","c","d","e"]', line=10)
            _sym(conn, f2, name="setupToolbar", body_hash="ht",
                 tokens='["a","b","c","d","e"]', line=20)
            # composable, >= 5 tokens → mantido.
            _sym(conn, f1, name="Row", kind="composable_fun", body_hash="hrow",
                 tokens='["a","b","c","d","e"]', line=30)
            _sym(conn, f2, name="Row", kind="composable_fun", body_hash="hrow",
                 tokens='["a","b","c","d","e"]', line=40)
            # trivial (<5 tokens) → filtrado pelo piso.
            _sym(conn, f1, name="setX", body_hash="hx", tokens='["a","b"]', line=50)
            _sym(conn, f2, name="setX", body_hash="hx", tokens='["a","b"]', line=60)
            # test-source dup (>=5 tokens) → excluído por path.
            t1 = _file(conn, "app/src/test/java/AlphaTest.kt", "app", source_set=None)
            t2 = _file(conn, "app/src/test/java/BetaTest.kt", "app", source_set=None)
            _sym(conn, t1, name="setUp", body_hash="hs",
                 tokens='["a","b","c","d","e"]', line=5)
            _sym(conn, t2, name="setUp", body_hash="hs",
                 tokens='["a","b","c","d","e"]', line=6)
    finally:
        conn.close()
    rows = queries.find_duplicates_within_module(tmp_path, db_path=db)
    assert {r["name"] for r in rows} == {"setupToolbar", "Row"}


def test_cross_read_broadened_bypasses_floor(tmp_path: Path) -> None:
    """Cross-module read-side bypassa o piso (2 tokens mantido). Regression
    guard do espelhamento cross-module."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _file(conn, "androidApp/src/main/kotlin/State.kt", "androidApp")
            f2 = _file(conn, "shared/src/commonMain/kotlin/State.kt", "shared",
                       source_set="commonMain", platform="common")
            _sym(conn, f1, name="update", body_hash="hu", tokens='["a","b"]',
                 line=5, receiver="MutableState")
            _sym(conn, f2, name="update", body_hash="hu", tokens='["a","b"]',
                 line=5, receiver="MutableState")
    finally:
        conn.close()
    rows = queries.find_duplicates_cross_module(tmp_path, db_path=db)
    assert {r["name"] for r in rows} == {"update"}
