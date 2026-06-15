"""H-01 regression: _reset_domain_tables must reject unknown table names.

WR-01 (final review 2026-06-15): the earlier version of this test re-inlined
the allowlist check into the test body and would have passed even if the
guard was removed from the implementation. This version drives the real
``_reset_domain_tables`` with a tampered ``tables=`` injection so the guard
under ``# noqa: S608`` is exercised genuinely.
"""

from __future__ import annotations

import sqlite3

import pytest

from engine.graph import builder


def test_reset_domain_tables_rejects_unknown_table():
    """Tampering with `tables` to inject an unknown table must raise.

    Drives the real function: pre-creates all allowlisted tables (so the
    DELETE loop wouldn't fail first on "no such table") and then calls
    ``_reset_domain_tables`` with a tampered list containing a single
    non-allowlisted name. The guard inside the function must raise
    ``ValueError`` BEFORE any DELETE runs.
    """
    conn = sqlite3.connect(":memory:")
    # Create only tables that ARE in the allowlist — so if the guard were
    # removed, the test would still detect that injecting a bogus name
    # bypassed validation (DELETE would fail with sqlite3.OperationalError,
    # not ValueError, surfacing the regression).
    for tbl in builder._ALLOWED_TABLES:
        conn.execute(f"CREATE TABLE {tbl} (id INTEGER PRIMARY KEY)")

    bad_name = "definitely_not_a_real_table"
    assert bad_name not in builder._ALLOWED_TABLES

    with pytest.raises(ValueError, match="Blocked unauthorized table wipe"):
        builder._reset_domain_tables(conn, tables=[bad_name])


def test_reset_domain_tables_default_uses_allowlisted_set():
    """The module-level default constant must be a subset of the allowlist.

    Belt-and-suspenders: catches accidental drift where a maintainer adds a
    new table to ``_DEFAULT_TABLES_TO_CLEAR`` without also adding it to
    ``_ALLOWED_TABLES``.
    """
    assert set(builder._DEFAULT_TABLES_TO_CLEAR).issubset(builder._ALLOWED_TABLES)
