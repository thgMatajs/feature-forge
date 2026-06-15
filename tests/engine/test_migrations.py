"""Tests pra migrations idempotentes (Mandamento #2 + AC-1).

Cobre ``engine.graph.builder._ensure_graph_body_column``: ALTER TABLE que
adiciona ``symbols.body TEXT`` em DBs legacy schema v2. Contract:

- Idempotente — chamadas subsequentes em DB já-migrado são no-op.
- Funciona em DB legacy (sem ``body``) — adiciona a coluna.
- Funciona em DB canônico (com ``body`` via ``init_schema``) — no-op.

Refs:
- docs/superpowers/specs/2026-06-12-graph-ia-evolution.md AC-1
- engine/graph/builder.py ``_ensure_graph_body_column``
"""

from __future__ import annotations

import sqlite3

import pytest

from engine.graph.builder import _ensure_graph_body_column
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
