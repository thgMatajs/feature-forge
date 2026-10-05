"""Universo ampliado da detecção de dup exata (GRAPH-REUSE-STAGE2 Task 1).

A detecção deixa de ser travada em extension functions
(`receiver_type IS NOT NULL` + `kind='fun'`) e passa a cobrir top-level `fun`
e `composable_fun` (os únicos kinds que carregam `body_hash`). Extension funs
(fun com receiver) permanecem cobertas.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.duplicates import detect_all_reuse_findings
from engine.utils.sqlite_io import open_db, transaction

# 5 tokens distintos → sobrevive ao piso REUSE_MIN_BODY_TOKENS introduzido na
# Task 2, mantendo este teste verde ao longo das Tasks 2 e 3.
_TOKENS5 = '["alpha","beta","gamma","delta","epsilon"]'


def _file(conn, path: str, module: str, source_set: str | None = "main") -> int:
    return conn.execute(
        "INSERT INTO files(path, language, module, source_set, platform) "
        "VALUES (?, 'kotlin', ?, ?, 'android')",
        (path, module, source_set),
    ).lastrowid


def _sym(conn, file_id: int, *, name: str, kind: str, receiver: str | None,
         body_hash: str, line: int, sig: str | None = None,
         tokens: str = _TOKENS5) -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind, signature, line_start, "
        "receiver_type, body_hash, body_tokens, modifiers) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')",
        (file_id, name, kind, sig or f"{name}()", line, receiver, body_hash, tokens),
    )


def _within_names(conn) -> set[str]:
    return {
        r["symbol_name"]
        for r in conn.execute(
            "SELECT symbol_name FROM reuse_findings "
            "WHERE category = 'duplicate-within-module'"
        ).fetchall()
    }


def test_broadened_universe_detects_toplevel_composable_and_extension(tmp_path: Path) -> None:
    """Top-level fun + composable_fun (sem receiver) + extension, todos
    duplicados within-module, produzem finding após o broadening.

    RED (código atual): só `fmt` (extension) é detectado — `setupToolbar`
    (top-level) e `LoadingRow` (composable) têm receiver NULL e são barrados
    por `receiver_type IS NOT NULL` + `kind='fun'`.
    """
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            a1 = _file(conn, "app/src/main/kotlin/A1.kt", "app")
            a2 = _file(conn, "app/src/main/kotlin/A2.kt", "app")
            # (a) top-level fun, sem receiver — hoje NÃO detectado.
            _sym(conn, a1, name="setupToolbar", kind="fun", receiver=None,
                 body_hash="ht", line=10)
            _sym(conn, a2, name="setupToolbar", kind="fun", receiver=None,
                 body_hash="ht", line=20)
            # (b) composable_fun, sem receiver — hoje NÃO detectado.
            _sym(conn, a1, name="LoadingRow", kind="composable_fun", receiver=None,
                 body_hash="hc", line=40)
            _sym(conn, a2, name="LoadingRow", kind="composable_fun", receiver=None,
                 body_hash="hc", line=50)
            # (c) extension fun, com receiver — hoje JÁ detectado (regression guard).
            _sym(conn, a1, name="fmt", kind="fun", receiver="Long",
                 body_hash="he", line=70, sig="Long.fmt(): String")
            _sym(conn, a2, name="fmt", kind="fun", receiver="Long",
                 body_hash="he", line=80, sig="Long.fmt(): String")
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        assert _within_names(conn) == {"setupToolbar", "LoadingRow", "fmt"}
    finally:
        conn.close()
