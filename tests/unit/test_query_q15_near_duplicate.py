"""Coverage — ``find_near_duplicates`` (Q15 in queries.py docstring).

Reports Kotlin extensions sharing ``(receiver_type, name, signature)`` but
declared with DIFFERENT ``body_hash`` values. Indicates accidental drift —
two helpers with identical signature whose implementations diverge.

The SQL contract is: same signature + ``COUNT(DISTINCT body_hash) > 1``.
The Jaccard / token-similarity threshold is applied by the *caller* in
``engine.graph.duplicates``, not at SQL level — these tests pin the
SQL-side contract.
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


def _insert_kt_ext(
    conn,
    file_id: int,
    *,
    name: str,
    receiver: str,
    signature: str,
    body_hash: str,
    line: int = 10,
) -> None:
    conn.execute(
        """
        INSERT INTO symbols(file_id, name, kind, signature, line_start,
                            receiver_type, body_hash, modifiers)
        VALUES (?, ?, 'fun', ?, ?, ?, ?, '')
        """,
        (file_id, name, signature, line, receiver, body_hash),
    )


def test_near_duplicate_same_signature_different_bodies(tmp_path: Path) -> None:
    """Two files declaring `Modifier.onFocusBlur(action)` with divergent bodies."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_file(conn, "feat/A.kt", "feature:auth")
            f2 = _insert_file(conn, "feat/B.kt", "feature:auth")
            _insert_kt_ext(
                conn, f1,
                name="onFocusBlur", receiver="Modifier",
                signature="onFocusBlur(action: () -> Unit): Modifier",
                body_hash="hA",
            )
            _insert_kt_ext(
                conn, f2,
                name="onFocusBlur", receiver="Modifier",
                signature="onFocusBlur(action: () -> Unit): Modifier",
                body_hash="hB",
            )
    finally:
        conn.close()

    rows = queries.find_near_duplicates(tmp_path, db_path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "onFocusBlur"
    assert row["receiver_type"] == "Modifier"
    assert row["n_bodies"] == 2
    assert row["n_files"] == 2
    # body_hashes is a GROUP_CONCAT — both must appear.
    assert set(row["body_hashes"].split(",")) == {"hA", "hB"}


def test_near_duplicate_same_body_hash_not_reported(tmp_path: Path) -> None:
    """Same signature AND same body_hash → not a near-duplicate (Q12/Q13 catch it)."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _insert_file(conn, "feat/A.kt", "feature:auth")
            f2 = _insert_file(conn, "feat/B.kt", "feature:auth")
            _insert_kt_ext(
                conn, f1,
                name="onFocusBlur", receiver="Modifier",
                signature="onFocusBlur(action: () -> Unit): Modifier",
                body_hash="hSAME",
            )
            _insert_kt_ext(
                conn, f2,
                name="onFocusBlur", receiver="Modifier",
                signature="onFocusBlur(action: () -> Unit): Modifier",
                body_hash="hSAME",
            )
    finally:
        conn.close()

    rows = queries.find_near_duplicates(tmp_path, db_path=db)
    # Only one DISTINCT body_hash → HAVING COUNT(DISTINCT) > 1 fails.
    assert rows == []
