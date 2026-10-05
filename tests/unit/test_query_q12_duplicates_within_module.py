"""Q12 coverage — ``find_duplicates_within_module``.

Seeds the graph DB with controlled Kotlin extension symbols and asserts:
- Happy: same (module, receiver_type, name, signature, body_hash) declared
  in 2+ files of the SAME module is reported.
- Negative: same shape but spread across DIFFERENT modules is NOT
  reported (that is Q13's job).
- Edge: rows with NULL body_hash are excluded from the result.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.utils.sqlite_io import open_db, transaction


def _insert_file(conn, path: str, module: str, source_set: str | None = "main") -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language, module, source_set) VALUES (?, ?, ?, ?)",
        (path, "kotlin", module, source_set),
    )
    return cur.lastrowid


def _insert_kt_extension(
    conn,
    file_id: int,
    *,
    name: str,
    receiver_type: str,
    signature: str,
    body_hash: str | None,
    line: int = 10,
    body_tokens: str = '["t1","t2","t3","t4","t5"]',
) -> None:
    conn.execute(
        """
        INSERT INTO symbols(file_id, name, kind, signature, line_start,
                            receiver_type, body_hash, body_tokens, modifiers)
        VALUES (?, ?, 'fun', ?, ?, ?, ?, ?, '')
        """,
        (file_id, name, signature, line, receiver_type, body_hash, body_tokens),
    )


def test_find_duplicates_within_module_happy_path(tmp_path: Path) -> None:
    """Two files in app:android both declare `String.formatDate` with same body."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_file(conn, "app/android/A.kt", "app:android")
            f2 = _insert_file(conn, "app/android/B.kt", "app:android")
            f3 = _insert_file(conn, "app/android/C.kt", "app:android")
            _insert_kt_extension(
                conn, f1, name="formatDate", receiver_type="String",
                signature="formatDate(): String", body_hash="h1",
            )
            _insert_kt_extension(
                conn, f2, name="formatDate", receiver_type="String",
                signature="formatDate(): String", body_hash="h1",
            )
            # Third file with a different body_hash for the same name —
            # should NOT count (signature+body_hash group differs).
            _insert_kt_extension(
                conn, f3, name="formatDate", receiver_type="String",
                signature="formatDate(): String", body_hash="h2",
            )
    finally:
        conn.close()

    rows = queries.find_duplicates_within_module(tmp_path, db_path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "formatDate"
    assert row["receiver_type"] == "String"
    assert row["module"] == "app:android"
    assert row["n"] == 2


def test_find_duplicates_within_module_cross_module_excluded(tmp_path: Path) -> None:
    """Same shape in DIFFERENT modules is Q13's responsibility — Q12 ignores it."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_file(conn, "app/android/A.kt", "app:android")
            f2 = _insert_file(conn, "shared/B.kt", "shared:foo")
            _insert_kt_extension(
                conn, f1, name="parseUrl", receiver_type="String",
                signature="parseUrl(): URL", body_hash="hX",
            )
            _insert_kt_extension(
                conn, f2, name="parseUrl", receiver_type="String",
                signature="parseUrl(): URL", body_hash="hX",
            )
    finally:
        conn.close()

    rows = queries.find_duplicates_within_module(tmp_path, db_path=db)
    assert rows == []


def test_find_duplicates_within_module_null_body_hash_excluded(tmp_path: Path) -> None:
    """Rows whose body_hash could not be computed (NULL) are excluded.

    Anonymous lambdas, unparseable bodies, and similar surface as
    ``body_hash IS NULL`` — they cannot ground a "duplicate" claim, so
    the SQL ``WHERE s.body_hash IS NOT NULL`` filters them out.
    """
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_file(conn, "app/android/A.kt", "app:android")
            f2 = _insert_file(conn, "app/android/B.kt", "app:android")
            _insert_kt_extension(
                conn, f1, name="opaqueExt", receiver_type="Foo",
                signature="opaqueExt(): Unit", body_hash=None,
            )
            _insert_kt_extension(
                conn, f2, name="opaqueExt", receiver_type="Foo",
                signature="opaqueExt(): Unit", body_hash=None,
            )
    finally:
        conn.close()

    rows = queries.find_duplicates_within_module(tmp_path, db_path=db)
    assert rows == []
