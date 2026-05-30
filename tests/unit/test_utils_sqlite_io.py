"""Unit tests — engine.utils.sqlite_io.

Exercises the schema bootstrap, transaction context manager, meta key-value
helpers and execute_many on the WAL-mode connection.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engine.utils import sqlite_io


def test_open_db_creates_schema(tmp_path):
    db = tmp_path / "g.db"
    conn = sqlite_io.open_db(db, create=True)
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        # A handful of canonical tables must be present per the DDL.
        assert {"files", "symbols", "features", "routes", "screens", "ds_components", "meta"} <= tables
    finally:
        conn.close()


def test_open_db_sets_wal_mode(tmp_path):
    db = tmp_path / "g.db"
    conn = sqlite_io.open_db(db, create=True)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        conn.close()


def test_open_db_foreign_keys_enabled(tmp_path):
    db = tmp_path / "g.db"
    conn = sqlite_io.open_db(db, create=True)
    try:
        on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert on == 1
    finally:
        conn.close()


def test_meta_round_trip(tmp_path):
    db = tmp_path / "g.db"
    conn = sqlite_io.open_db(db, create=True)
    try:
        # schema_version is stamped on init.
        assert sqlite_io.fetch_meta(conn, "schema_version") == sqlite_io.SCHEMA_VERSION
        sqlite_io.set_meta(conn, "custom-key", "v1")
        assert sqlite_io.fetch_meta(conn, "custom-key") == "v1"
        # Upsert overwrites.
        sqlite_io.set_meta(conn, "custom-key", "v2")
        assert sqlite_io.fetch_meta(conn, "custom-key") == "v2"
        assert sqlite_io.fetch_meta(conn, "no-such-key") is None
    finally:
        conn.close()


def test_transaction_commits_on_success(tmp_path):
    db = tmp_path / "g.db"
    conn = sqlite_io.open_db(db, create=True)
    try:
        with sqlite_io.transaction(conn):
            conn.execute(
                "INSERT INTO features(slug, status) VALUES (?, ?)",
                ("alpha", "planned"),
            )
        row = conn.execute("SELECT slug, status FROM features").fetchone()
        assert row["slug"] == "alpha"
        assert row["status"] == "planned"
    finally:
        conn.close()


def test_transaction_rolls_back_on_exception(tmp_path):
    db = tmp_path / "g.db"
    conn = sqlite_io.open_db(db, create=True)
    try:
        with pytest.raises(RuntimeError):
            with sqlite_io.transaction(conn):
                conn.execute(
                    "INSERT INTO features(slug, status) VALUES (?, ?)",
                    ("rolled-back", "planned"),
                )
                raise RuntimeError("boom")
        count = conn.execute("SELECT COUNT(*) AS n FROM features").fetchone()["n"]
        assert count == 0
    finally:
        conn.close()


def test_execute_many_bulk_insert(tmp_path):
    db = tmp_path / "g.db"
    conn = sqlite_io.open_db(db, create=True)
    try:
        rows = [("a", "planned"), ("b", "implementing"), ("c", "done")]
        with sqlite_io.transaction(conn):
            sqlite_io.execute_many(
                conn,
                "INSERT INTO features(slug, status) VALUES (?, ?)",
                rows,
            )
        assert conn.execute("SELECT COUNT(*) AS n FROM features").fetchone()["n"] == 3
    finally:
        conn.close()


def test_init_schema_is_idempotent(tmp_path):
    db = tmp_path / "g.db"
    conn = sqlite_io.open_db(db, create=True)
    try:
        # Re-initing must not raise.
        sqlite_io.init_schema(conn)
        sqlite_io.init_schema(conn)
    finally:
        conn.close()
