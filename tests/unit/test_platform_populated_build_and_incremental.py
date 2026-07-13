"""Population of `files.platform` on full build + incremental re-ingest."""

from __future__ import annotations

from pathlib import Path

from engine.graph import incremental
from engine.graph.builder import build_full
from engine.utils.sqlite_io import open_db


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_tree(proj: Path) -> None:
    _write(proj / "settings.gradle.kts",
           'include(":shared")\ninclude(":app")\ninclude(":iosApp")\n')
    # Common (KMP source-set).
    _write(proj / "shared" / "src" / "commonMain" / "kotlin" / "Fmt.kt",
           "package x\nfun Long.fmt(): String = \"\"\n")
    # Android in standard /src/main/ layout (no KMP source-set).
    _write(proj / "app" / "src" / "main" / "kotlin" / "Home.kt",
           "package x\nclass Home\n")
    # iOS Swift under Xcode layout.
    _write(proj / "iosApp" / "Sources" / "HomeView.swift",
           "import SwiftUI\nstruct HomeView: View { var body: some View { Text(\"x\") } }\n")


def _platform_of(conn, suffix: str) -> str | None:
    row = conn.execute(
        "SELECT platform FROM files WHERE path LIKE ?", (f"%{suffix}",)
    ).fetchone()
    assert row is not None, f"no file row for {suffix}"
    return row["platform"]


def test_build_full_populates_platform(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    _build_tree(proj)
    db = proj / "graph.db"
    build_full(proj, db_path=db)
    conn = open_db(db, create=False)
    try:
        assert _platform_of(conn, "shared/src/commonMain/kotlin/Fmt.kt") == "common"
        assert _platform_of(conn, "app/src/main/kotlin/Home.kt") == "android"
        assert _platform_of(conn, "iosApp/Sources/HomeView.swift") == "ios"
    finally:
        conn.close()


def test_incremental_reingest_keeps_platform(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    _build_tree(proj)
    db = proj / "graph.db"
    build_full(proj, db_path=db)
    home = proj / "app" / "src" / "main" / "kotlin" / "Home.kt"
    home.write_text("package x\nclass Home { val v = 1 }\n", encoding="utf-8")
    incremental.update_file(proj, home, db_path=db)
    conn = open_db(db, create=False)
    try:
        assert _platform_of(conn, "app/src/main/kotlin/Home.kt") == "android"
    finally:
        conn.close()
