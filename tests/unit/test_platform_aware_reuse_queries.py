"""Platform-aware `redundant-platform-specific` + `kmp-migration-candidate`.

The Android redundant copy lives under `app/src/main/` (module `app`,
source_set NULL) — the pre-Stage-1 heuristic (`module LIKE 'androidApp%'` or
`source_set='androidMain'`) misses it. The platform-aware query catches it via
`files.platform='android'`.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.graph.duplicates import detect_all_reuse_findings
from engine.utils.sqlite_io import open_db, transaction


def _insert_file(conn, path, module, source_set, platform, language="kotlin") -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language, module, source_set, platform) "
        "VALUES (?, ?, ?, ?, ?)",
        (path, language, module, source_set, platform),
    )
    return cur.lastrowid


def _insert_kt_ext(conn, file_id, *, name="formatTime", receiver="Long",
                   sig="formatTime(): String", body_hash="hZ", tokens='["a","b"]',
                   line=10) -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind, signature, line_start, "
        "receiver_type, body_hash, body_tokens, modifiers) "
        "VALUES (?, ?, 'fun', ?, ?, ?, ?, ?, '')",
        (file_id, name, sig, line, receiver, body_hash, tokens),
    )


def _insert_swift_func(conn, file_id, *, name="formatTime", receiver="Long",
                       sig="formatTime() -> String", tokens='["a","b"]', line=5) -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind, signature, line_start, "
        "receiver_type, body_hash, body_tokens, modifiers) "
        "VALUES (?, ?, 'func', ?, ?, ?, NULL, ?, '')",
        (file_id, name, sig, line, receiver, tokens),
    )


def test_read_query_redundant_catches_src_main_android(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            shared_f = _insert_file(
                conn, "shared/src/commonMain/kotlin/Time.kt",
                "shared", "commonMain", "common")
            android_f = _insert_file(
                conn, "app/src/main/kotlin/Time.kt",
                "app", None, "android")
            _insert_kt_ext(conn, shared_f)
            _insert_kt_ext(conn, android_f)
    finally:
        conn.close()
    rows = queries.find_redundant_platform_specific(tmp_path, db_path=db)
    assert len(rows) == 1
    assert rows[0]["name"] == "formatTime"
    assert rows[0]["shared_module"] == "shared"
    assert rows[0]["android_module"] == "app"


def test_detection_materializes_redundant_finding(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            shared_f = _insert_file(
                conn, "shared/src/commonMain/kotlin/Time.kt",
                "shared", "commonMain", "common")
            android_f = _insert_file(
                conn, "app/src/main/kotlin/Time.kt",
                "app", None, "android")
            _insert_kt_ext(conn, shared_f)
            _insert_kt_ext(conn, android_f)
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM reuse_findings "
            "WHERE category = 'redundant-platform-specific'"
        ).fetchone()["c"]
        assert n == 1
    finally:
        conn.close()


def test_kmp_migration_gated_by_common_platform(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            kt_f = _insert_file(
                conn, "shared/src/commonMain/kotlin/Time.kt",
                "shared", "commonMain", "common")
            sw_f = _insert_file(
                conn, "iosApp/Sources/Time.swift",
                "iosApp", None, "ios", language="swift")
            _insert_kt_ext(conn, kt_f)
            _insert_swift_func(conn, sw_f)
    finally:
        conn.close()
    rows = queries.find_kmp_migration_candidates(tmp_path, db_path=db)
    assert len(rows) == 1
    assert rows[0]["name"] == "formatTime"
    assert rows[0]["kotlin_module"] == "shared"
    assert rows[0]["swift_module"] == "iosApp"
