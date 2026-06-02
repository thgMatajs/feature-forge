"""Coverage — ``find_kmp_migration_candidates``.

Reports Swift extensions whose ``(receiver, name)`` mirrors a Kotlin
extension on the **shared / commonMain** side. Such Swift duplicates are
candidates to replace with a SKIE call into the shared module.

The Kotlin side MUST satisfy:
- ``s.kind = 'fun'`` with non-null ``receiver_type``
- file path ``LIKE '%.kt'``
- module ``= 'shared'`` OR ``LIKE 'shared:%'``
- ``source_set = 'commonMain'`` OR ``IS NULL``

The Swift side:
- ``s.kind = 'func'`` with non-null ``receiver_type``
- file path ``LIKE '%.swift'``

Token-similarity (Jaccard) is caller-side — these tests pin the SQL.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.utils.sqlite_io import open_db, transaction


def _insert_kt_shared(conn, path: str, name: str, receiver: str) -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language, module, source_set) "
        "VALUES (?, 'kotlin', 'shared:core', 'commonMain')",
        (path,),
    )
    file_id = cur.lastrowid
    conn.execute(
        """
        INSERT INTO symbols(file_id, name, kind, signature, line_start,
                            receiver_type, body_hash, body_tokens, modifiers)
        VALUES (?, ?, 'fun', ?, 10, ?, 'hkt', '["fmt","date"]', '')
        """,
        (file_id, name, f"{name}(): String", receiver),
    )
    return file_id


def _insert_swift(conn, path: str, name: str, receiver: str, module: str = "ios:app") -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language, module, source_set) "
        "VALUES (?, 'swift', ?, NULL)",
        (path, module),
    )
    file_id = cur.lastrowid
    conn.execute(
        """
        INSERT INTO symbols(file_id, name, kind, signature, line_start,
                            receiver_type, body_hash, body_tokens, modifiers)
        VALUES (?, ?, 'func', ?, 20, ?, 'hsw', '["fmt","date"]', '')
        """,
        (file_id, name, f"{name}() -> String", receiver),
    )
    return file_id


def test_kmp_migration_candidate_swift_mirror_of_shared_kotlin(tmp_path: Path) -> None:
    """Swift extension matching a shared:commonMain Kotlin one → flagged."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            _insert_kt_shared(conn, "shared/core/Date.kt", "formatDate", "Date")
            _insert_swift(conn, "ios/Date+Ext.swift", "formatDate", "Date")
    finally:
        conn.close()

    rows = queries.find_kmp_migration_candidates(tmp_path, db_path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "formatDate"
    assert row["receiver"] == "Date"
    assert row["kotlin_module"] == "shared:core"
    assert row["kotlin_source_set"] == "commonMain"
    assert row["swift_path"].endswith("Date+Ext.swift")


def test_kmp_migration_candidate_no_swift_peer(tmp_path: Path) -> None:
    """Kotlin shared symbol with NO matching Swift declaration → no candidate."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            _insert_kt_shared(conn, "shared/core/Date.kt", "formatDate", "Date")
    finally:
        conn.close()

    rows = queries.find_kmp_migration_candidates(tmp_path, db_path=db)
    assert rows == []
