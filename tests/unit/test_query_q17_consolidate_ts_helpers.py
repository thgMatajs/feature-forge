"""Coverage — ``find_duplicate_ts_helpers``.

Reports TypeScript / JavaScript top-level helpers (``kind = 'function'``,
no receiver) declared 2+ times within ONE Gradle / pnpm module with
identical body_hash. Fuels the consolidate-ts-helper proposal.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.utils.sqlite_io import open_db, transaction


def _insert_ts_file(conn, path: str, module: str) -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language, module, source_set) "
        "VALUES (?, 'typescript', ?, NULL)",
        (path, module),
    )
    return cur.lastrowid


def _insert_ts_helper(conn, file_id: int, name: str, body_hash: str) -> None:
    conn.execute(
        """
        INSERT INTO symbols(file_id, name, kind, signature, line_start,
                            receiver_type, body_hash, modifiers)
        VALUES (?, ?, 'function', ?, 1, NULL, ?, '')
        """,
        (file_id, name, f"function {name}(s: string): string", body_hash),
    )


def test_q17_two_files_same_module_same_body(tmp_path: Path) -> None:
    """`slugify` declared in two .ts files in same module with same body_hash."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_ts_file(conn, "web/src/util/slug.ts", "web:app")
            f2 = _insert_ts_file(conn, "web/src/feature/slug.ts", "web:app")
            _insert_ts_helper(conn, f1, "slugify", "hSL")
            _insert_ts_helper(conn, f2, "slugify", "hSL")
    finally:
        conn.close()

    rows = queries.find_duplicate_ts_helpers(tmp_path, db_path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "slugify"
    assert row["module"] == "web:app"
    assert row["n"] == 2


def test_q17_single_file_not_picked_up(tmp_path: Path) -> None:
    """Single declaration → COUNT(*) = 1, HAVING > 1 fails, no row reported."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_ts_file(conn, "web/src/util/slug.ts", "web:app")
            _insert_ts_helper(conn, f1, "slugify", "hSL")
    finally:
        conn.close()

    rows = queries.find_duplicate_ts_helpers(tmp_path, db_path=db)
    assert rows == []
