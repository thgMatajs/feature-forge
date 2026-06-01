"""Regression: ``_reset_domain_tables`` must restore FK pragma on error (C3).

Bug C3 (PR #1): the function runs ``PRAGMA foreign_keys = OFF`` → DELETEs →
``PRAGMA foreign_keys = ON``. If any DELETE raises, the second PRAGMA never
runs and the connection leaks ``foreign_keys = OFF`` into subsequent
transactions — silently disabling FK enforcement project-wide for the
remainder of the connection's life.

Fix: wrap DELETEs in an explicit ``try/finally`` that always restores
``PRAGMA foreign_keys = ON``. Inside the ``try`` the DELETEs run inside an
implicit transaction (``with conn:``) so a mid-stream failure rolls back —
no partial wipe.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engine.graph.builder import _reset_domain_tables
from engine.utils.sqlite_io import open_db


def _fk_pragma_state(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA foreign_keys").fetchone()[0]


def test_reset_domain_tables_happy_path_restores_fk_pragma(tmp_path: Path):
    """Happy path: FK pragma ends ON, all tables empty."""
    db_path = tmp_path / "graph.db"
    conn = open_db(db_path, create=True)
    try:
        assert _fk_pragma_state(conn) == 1, "open_db sets foreign_keys ON"
        _reset_domain_tables(conn)
        assert _fk_pragma_state(conn) == 1, (
            "After reset, FK pragma must remain ON"
        )
        # Sanity: tables are empty.
        for table in ("files", "symbols", "imports"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0
    finally:
        conn.close()


class _FailingConn:
    """Thin proxy that delegates to a real Connection but fails on Nth DELETE.

    `sqlite3.Connection.execute` is read-only on the C side, so we proxy the
    whole object instead of patching the method.
    """

    def __init__(self, real: sqlite3.Connection, fail_on_delete_n: int):
        self._real = real
        self._fail_on = fail_on_delete_n
        self._delete_count = 0

    def execute(self, sql, *args, **kwargs):
        if sql.strip().upper().startswith("DELETE FROM"):
            self._delete_count += 1
            if self._delete_count == self._fail_on:
                raise sqlite3.OperationalError("simulated DELETE failure")
        return self._real.execute(sql, *args, **kwargs)

    def __enter__(self):
        return self._real.__enter__()

    def __exit__(self, exc_type, exc, tb):
        return self._real.__exit__(exc_type, exc, tb)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_reset_domain_tables_restores_fk_pragma_on_error(tmp_path: Path):
    """If a DELETE raises, FK pragma must still be restored to ON."""
    db_path = tmp_path / "graph.db"
    real_conn = open_db(db_path, create=True)
    try:
        assert _fk_pragma_state(real_conn) == 1

        wrapped = _FailingConn(real_conn, fail_on_delete_n=2)

        with pytest.raises(sqlite3.OperationalError, match="simulated"):
            _reset_domain_tables(wrapped)

        # The critical assertion — without the try/finally fix this is 0.
        assert _fk_pragma_state(real_conn) == 1, (
            "FK pragma must be restored to ON even when a DELETE raises"
        )
    finally:
        real_conn.close()
