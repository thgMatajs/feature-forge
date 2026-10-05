"""Coverage — ``find_redundant_platform_specific``.

Reports Kotlin extensions defined in BOTH a ``shared:* / commonMain`` source
set AND a platform-specific (``shared:* / androidMain`` or
``androidApp%`` module) location with identical body_hash. The
platform-specific copy is redundant — consumers should use the shared
implementation.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.utils.sqlite_io import open_db, transaction


def _insert_file(
    conn,
    path: str,
    module: str,
    source_set: str | None,
    platform: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language, module, source_set, platform) "
        "VALUES (?, ?, ?, ?, ?)",
        (path, "kotlin", module, source_set, platform),
    )
    return cur.lastrowid


def _insert_kt_ext(
    conn,
    file_id: int,
    *,
    name: str = "formatTime",
    receiver_type: str = "Long",
    signature: str = "formatTime(): String",
    body_hash: str = "hY",
    line: int = 10,
) -> None:
    conn.execute(
        """
        INSERT INTO symbols(file_id, name, kind, signature, line_start,
                            receiver_type, body_hash, modifiers)
        VALUES (?, ?, 'fun', ?, ?, ?, ?, '')
        """,
        (file_id, name, signature, line, receiver_type, body_hash),
    )


def test_redundant_platform_shared_and_android(tmp_path: Path) -> None:
    """`shared:foo / commonMain` + identical `androidApp:core` copy → redundant."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            shared_f = _insert_file(
                conn,
                "shared/foo/Time.kt",
                module="shared:foo",
                source_set="commonMain",
                platform="common",
            )
            android_f = _insert_file(
                conn,
                "androidApp/core/Time.kt",
                module="androidApp:core",
                source_set="main",
                platform="android",
            )
            _insert_kt_ext(conn, shared_f)
            _insert_kt_ext(conn, android_f)
    finally:
        conn.close()

    rows = queries.find_redundant_platform_specific(tmp_path, db_path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "formatTime"
    assert row["shared_module"] == "shared:foo"
    assert row["android_module"] == "androidApp:core"
    assert row["body_hash"] == "hY"


def test_redundant_platform_no_shared_peer(tmp_path: Path) -> None:
    """Symbol only in `androidApp:core` (no shared/commonMain peer) → NOT redundant."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            android_f = _insert_file(
                conn,
                "androidApp/core/Time.kt",
                module="androidApp:core",
                source_set="main",
                platform="android",
            )
            _insert_kt_ext(conn, android_f)
    finally:
        conn.close()

    rows = queries.find_redundant_platform_specific(tmp_path, db_path=db)
    assert rows == []
