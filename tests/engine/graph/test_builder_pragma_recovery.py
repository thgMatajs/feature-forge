"""H-04 regression: PRAGMA finally must not mask the original exception."""

from __future__ import annotations

import sqlite3

import pytest

from engine.graph import builder


class _ConnWrapper:
    """Pass-through wrapper that lets us intercept .execute() calls.

    sqlite3.Connection.execute is read-only (cannot monkeypatch directly),
    so we delegate via a thin wrapper class instead.
    """

    def __init__(self, real_conn, on_pragma_on):
        self._conn = real_conn
        self._on_pragma_on = on_pragma_on

    def execute(self, sql, *args, **kwargs):
        if sql == "PRAGMA foreign_keys = ON":
            return self._on_pragma_on()
        return self._conn.execute(sql, *args, **kwargs)

    @property
    def in_transaction(self):
        return self._conn.in_transaction

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


def test_reset_domain_tables_pragma_finally_swallows_pragma_error():
    """If PRAGMA-on raises in finally, the function must not propagate it.

    We force the PRAGMA in `finally` to raise via a wrapper connection.
    The function should swallow the secondary PRAGMA error so it does not
    mask any prior exception from the DELETE block (best-effort restore).
    """
    real = sqlite3.connect(":memory:")
    # Create all allowlisted tables so the DELETE loop succeeds and the
    # finally branch is reached cleanly (the test exercises ONLY the
    # finally-swallow behavior, not failure mid-DELETE).
    for tbl in builder._ALLOWED_TABLES:
        real.execute(f"CREATE TABLE {tbl} (id INTEGER PRIMARY KEY)")

    pragma_calls = {"n": 0}

    def break_on_pragma_on():
        pragma_calls["n"] += 1
        raise sqlite3.OperationalError("connection closed")

    conn = _ConnWrapper(real, break_on_pragma_on)

    # Should NOT raise — the PRAGMA-on failure in finally is swallowed.
    builder._reset_domain_tables(conn)
    assert pragma_calls["n"] == 1
