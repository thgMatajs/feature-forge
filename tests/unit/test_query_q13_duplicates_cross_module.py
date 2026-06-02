"""Q13 coverage — ``find_duplicates_cross_module``.

Reports Kotlin extensions with identical body_hash declared across MORE
than one Gradle module — fuels ``promote-to-shared-helper``.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.utils.sqlite_io import open_db, transaction


def _insert_file(conn, path: str, module: str) -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language, module, source_set) VALUES (?, ?, ?, 'main')",
        (path, "kotlin", module),
    )
    return cur.lastrowid


def _insert_kt_ext(conn, file_id: int, name: str, body_hash: str) -> None:
    conn.execute(
        """
        INSERT INTO symbols(file_id, name, kind, signature, line_start,
                            receiver_type, body_hash, modifiers)
        VALUES (?, ?, 'fun', ?, 10, 'String', ?, '')
        """,
        (file_id, name, f"{name}(): URL", body_hash),
    )


def test_q13_happy_two_modules_same_body(tmp_path: Path) -> None:
    """Same body_hash in two distinct modules → reported as cross-module dup."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_file(conn, "app/android/A.kt", "app:android")
            f2 = _insert_file(conn, "shared/B.kt", "shared:foo")
            _insert_kt_ext(conn, f1, "parseUrl", "hX")
            _insert_kt_ext(conn, f2, "parseUrl", "hX")
    finally:
        conn.close()

    rows = queries.find_duplicates_cross_module(tmp_path, db_path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "parseUrl"
    assert row["n_modules"] == 2
    # GROUP_CONCAT(DISTINCT module) — order is implementation-defined.
    modules = set(row["modules"].split(","))
    assert modules == {"app:android", "shared:foo"}


def test_q13_negative_same_module_excluded(tmp_path: Path) -> None:
    """Two files in the SAME module is Q12 territory — Q13 must not pick up."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_file(conn, "app/android/A.kt", "app:android")
            f2 = _insert_file(conn, "app/android/B.kt", "app:android")
            _insert_kt_ext(conn, f1, "parseUrl", "hX")
            _insert_kt_ext(conn, f2, "parseUrl", "hX")
    finally:
        conn.close()

    rows = queries.find_duplicates_cross_module(tmp_path, db_path=db)
    assert rows == []


def test_q13_grouping_three_modules(tmp_path: Path) -> None:
    """Same body_hash across THREE distinct modules → single grouped row with n_modules=3."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_file(conn, "app/android/A.kt", "app:android")
            f2 = _insert_file(conn, "shared/B.kt", "shared:foo")
            f3 = _insert_file(conn, "feature/auth/C.kt", "feature:auth")
            _insert_kt_ext(conn, f1, "slugify", "hZ")
            _insert_kt_ext(conn, f2, "slugify", "hZ")
            _insert_kt_ext(conn, f3, "slugify", "hZ")
    finally:
        conn.close()

    rows = queries.find_duplicates_cross_module(tmp_path, db_path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["n_modules"] == 3
    assert row["n_files"] == 3
    assert set(row["modules"].split(",")) == {
        "app:android",
        "shared:foo",
        "feature:auth",
    }
