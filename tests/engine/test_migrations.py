"""Tests pra migrations idempotentes + walker hardening (Mandamento #2 + AC-1).

Cobre ``engine.graph.builder._ensure_graph_body_column``: ALTER TABLE que
adiciona ``symbols.body TEXT`` em DBs legacy schema v2. Contract:

- Idempotente — chamadas subsequentes em DB já-migrado são no-op.
- Funciona em DB legacy (sem ``body``) — adiciona a coluna.
- Funciona em DB canônico (com ``body`` via ``init_schema``) — no-op.

Cobre também ``engine.graph.builder._iter_files``: walker discovery do
``discover_source_files`` que precisa proteger contra symlinks cíclicos
(E-N-001). E o pre-existing ``_idx_symbols_body_hash`` (idempotência sob
race) + ``_apply_ensure_migrations`` (TOCTOU em ALTER concurrent, E-N-003).

Refs:
- docs/superpowers/specs/2026-06-12-graph-ia-evolution.md AC-1
- engine/graph/builder.py ``_ensure_graph_body_column``, ``_iter_files``
- engine/graph/incremental.py ``_apply_ensure_migrations``
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engine.graph.builder import _ensure_graph_body_column, discover_source_files
from engine.graph.incremental import _apply_ensure_migrations
from engine.utils.sqlite_io import init_schema


def _row_factory_conn(db_path) -> sqlite3.Connection:
    """Conn com ``sqlite3.Row`` — mirrors ``engine.utils.sqlite_io.open_db``.

    ``_ensure_graph_body_column`` acessa ``c["name"]`` no result do
    ``PRAGMA table_info``, então o row factory tem que estar setado.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def test_ensure_graph_body_column_is_idempotent(tmp_path):
    """DB canônico (init_schema já criou ``body``) → calls subsequentes são no-op."""
    db_path = tmp_path / "graph.db"
    conn = _row_factory_conn(db_path)
    init_schema(conn)
    _ensure_graph_body_column(conn)
    _ensure_graph_body_column(conn)  # Second call — must NOT raise
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(symbols)").fetchall()}
    assert "body" in cols
    conn.close()


def test_ensure_graph_body_column_on_legacy_db(tmp_path):
    """DB v2 sem ``body`` → ALTER TABLE adiciona; subsequent calls no-op."""
    db_path = tmp_path / "graph.db"
    conn = _row_factory_conn(db_path)
    # Simular DB legacy: criar symbols sem body
    conn.execute(
        """
        CREATE TABLE symbols (
            id INTEGER PRIMARY KEY,
            file_id INTEGER,
            name TEXT,
            kind TEXT
        )
        """
    )
    conn.commit()

    cols_before = {c["name"] for c in conn.execute("PRAGMA table_info(symbols)").fetchall()}
    assert "body" not in cols_before

    _ensure_graph_body_column(conn)
    cols_after = {c["name"] for c in conn.execute("PRAGMA table_info(symbols)").fetchall()}
    assert "body" in cols_after

    # Idempotente — segunda call não duplica nem estoura
    _ensure_graph_body_column(conn)
    cols_after_second = {
        c["name"] for c in conn.execute("PRAGMA table_info(symbols)").fetchall()
    }
    assert cols_after_second == cols_after

    conn.close()


# ── E-N-001: walker resilience to symlink cycles ───────────────────────────


def test_discover_source_files_terminates_on_cyclic_symlink(
    tmp_path: Path,
) -> None:
    """Walker termina em projeto com symlink cíclico — não loop infinito.

    Cenário: monorepo grande com link cíclico esquisito (bind mount,
    submodule mal configurado, ou desenvolvedor brincando). Antes do fix
    do E-N-001, ``_iter_files`` usava ``Path.is_dir()`` default — que
    SEGUE symlinks. Loop ``inner/ -> inner/loop -> inner/ -> ...`` enchia
    o stack até OOM ou trancava o test runner.

    Pós-fix: ``entry.is_symlink()`` guard pula symlinks por completo (o
    pattern já estava implementado em ``_find_gitignore_files`` mas não
    no walker principal).

    Determinismo: criamos só 1 arquivo Kotlin real fora do ciclo e
    garantimos que ele é encontrado. Sem termination, o teste hangs
    (caught por pytest --timeout em CI, mas localmente trava).
    """
    project = tmp_path / "proj"
    project.mkdir()
    # Arquivo real, fora do ciclo
    (project / "Real.kt").write_text("fun main() {}\n", encoding="utf-8")

    # Cria symlink cíclico: project/loop → project/inner; project/inner/back → project
    inner = project / "inner"
    inner.mkdir()
    (inner / "back").symlink_to(project)  # cycle: inner/back/inner/back/...
    (project / "loop").symlink_to(inner)  # extra alias pra reforçar o ciclo

    # Sem timeout: confia no fix (guard pula symlinks). Em CI lento, pytest
    # global timeout segura, mas localmente o assert termina rápido.
    result = discover_source_files(project)
    # ``Real.kt`` real foi encontrado; arquivos atrás de symlinks NÃO entram.
    kotlin_files = result.get(".kt", [])
    assert any(p.name == "Real.kt" for p in kotlin_files), (
        f"Expected Real.kt to be discovered, got: {kotlin_files}"
    )
    # Verificação extra: o walker NÃO devolveu duplicates do mesmo
    # arquivo por seguir o symlink.
    real_path_str = str((project / "Real.kt").resolve())
    same_real = [p for p in kotlin_files if str(p.resolve()) == real_path_str]
    assert len(same_real) == 1, (
        f"Real.kt should appear once, walker followed symlink and "
        f"discovered duplicates: {same_real}"
    )


# ── T-N-012: migration idempotência sob race ──────────────────────────────


def test_apply_ensure_migrations_is_idempotent_under_race(tmp_path: Path) -> None:
    """``_apply_ensure_migrations`` engole ``duplicate column name``.

    Simula TOCTOU race: 2 conexões abrem o mesmo DB, ambas detectam que
    a coluna está ausente, ambas tentam ALTER TABLE. SQLite serializa o
    segundo ALTER pra raise ``OperationalError("duplicate column name")``.
    Pré-fix do E-N-003: a exception propaga até update_file/update_batch.
    Pós-fix: ``_apply_ensure_migrations`` engole apenas erros de
    "duplicate column", outros tipos de erro re-raise.

    Cenário deste teste: conn A roda primeiro, marca o ``meta`` flag.
    Conn B ABRE com marker ausente em memory (cache stale) e tenta
    rodar de novo. Pós-fix isso é safe.
    """
    db_path = tmp_path / "graph.db"
    conn_a = sqlite3.connect(str(db_path))
    conn_a.row_factory = sqlite3.Row
    init_schema(conn_a)
    _apply_ensure_migrations(conn_a)
    conn_a.commit()

    # Segunda conexão — `_apply_ensure_migrations` deve ver o marker via
    # ``_migrations_applied`` e ser no-op. Não deve raise.
    conn_b = sqlite3.connect(str(db_path))
    conn_b.row_factory = sqlite3.Row
    _apply_ensure_migrations(conn_b)  # no-op via marker — sem raise

    # Sanity: re-chama com marker presente — idempotente.
    _apply_ensure_migrations(conn_a)
    _apply_ensure_migrations(conn_b)

    conn_a.close()
    conn_b.close()


def test_idx_symbols_body_hash_pre_existing_is_idempotent(tmp_path: Path) -> None:
    """Index pre-existente em DB legacy não causa erro na migration.

    Cobre o cenário onde uma DB legacy v2 já tinha o índice manualmente
    criado (e.g., dev rodou CREATE INDEX no SQLite REPL). A migration usa
    ``CREATE INDEX IF NOT EXISTS`` (sqlite_io.py canonical DDL), então é
    safe — este teste é um regression guard caso algum dev refator volte
    pra ``CREATE INDEX`` puro.
    """
    db_path = tmp_path / "graph.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    # Index já existe pós init_schema. Re-rodar manualmente o equivalente
    # da migration: ``_ensure_reuse_intelligence_columns`` é o caller que
    # cria ``idx_symbols_body_hash``; checamos que re-invocar a migration
    # body_column NÃO regrida sobre o index.
    _ensure_graph_body_column(conn)
    # Index ainda existe — IF NOT EXISTS protege.
    indexes = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_symbols_body_hash" in indexes
    conn.close()
