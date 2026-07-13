"""Schema guard — `files.platform` column (GRAPH-REAL-REPO Stage 1, no bump)."""

from __future__ import annotations

from pathlib import Path

from engine.graph import incremental
from engine.graph.builder import _ensure_platform_column, build_full
from engine.utils.sqlite_io import open_db


def _platform_columns(conn) -> set[str]:
    return {c["name"] for c in conn.execute("PRAGMA table_info(files)").fetchall()}


def test_fresh_db_ddl_has_platform_column(tmp_path: Path) -> None:
    # open_db(create=True) runs the canonical DDL from sqlite_io: it provides
    # the `platform` COLUMN. The `idx_files_platform` INDEX vive na migração
    # `_ensure_platform_column` (não no DDL — evita crash de init_schema em DB
    # legado; ver 04-pending), chamada por build_full/incremental pós-open_db.
    conn = open_db(tmp_path / "fresh.db", create=True)
    try:
        assert "platform" in _platform_columns(conn)
        _ensure_platform_column(conn)
        idx = {r["name"] for r in conn.execute(
            "PRAGMA index_list(files)"
        ).fetchall()}
        assert "idx_files_platform" in idx
    finally:
        conn.close()


def test_ensure_platform_column_is_idempotent(tmp_path: Path) -> None:
    conn = open_db(tmp_path / "legacy.db", create=True)
    try:
        # Simulate a legacy DB that predates the canonical DDL change.
        conn.execute("DROP INDEX IF EXISTS idx_files_platform")
        try:
            conn.execute("ALTER TABLE files DROP COLUMN platform")
        except Exception:
            pass
        assert "platform" not in _platform_columns(conn)
        _ensure_platform_column(conn)
        assert "platform" in _platform_columns(conn)
        # Second call must be a no-op (no exception).
        _ensure_platform_column(conn)
        assert "platform" in _platform_columns(conn)
    finally:
        conn.close()


def test_build_full_creates_platform_column(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "A.kt").write_text("package x\nclass A\n", encoding="utf-8")
    db = proj / "graph.db"
    build_full(proj, db_path=db)
    conn = open_db(db, create=False)
    try:
        assert "platform" in _platform_columns(conn)
    finally:
        conn.close()


def test_incremental_migration_adds_column_despite_stale_marker(
    tmp_path: Path,
) -> None:
    """A DB stamped with the OLD marker must still gain `platform`."""
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    f = proj / "src" / "A.kt"
    f.write_text("package x\nclass A\n", encoding="utf-8")
    db = proj / "graph.db"
    conn = open_db(db, create=True)
    try:
        # Drop the column and stamp the STALE marker to prove the bump works.
        conn.execute("DROP INDEX IF EXISTS idx_files_platform")
        try:
            conn.execute("ALTER TABLE files DROP COLUMN platform")
        except Exception:
            pass
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) "
            "VALUES ('migrations_applied_v1_3', '1')"
        )
        conn.commit()
    finally:
        conn.close()
    incremental.update_file(proj, f, db_path=db)
    conn = open_db(db, create=False)
    try:
        assert "platform" in _platform_columns(conn)
    finally:
        conn.close()
