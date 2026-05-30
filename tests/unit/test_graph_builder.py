"""Unit tests — engine.graph.builder.

Exercises discover_source_files exclusions, infers feature slug from path,
and the full build_full() pipeline against a minimal synthetic project.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import builder
from engine.utils.sqlite_io import open_db


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discover_source_files_excludes_build_dirs(tmp_path):
    _write(tmp_path / "src" / "A.kt", "package x\nclass A\n")
    _write(tmp_path / "build" / "X.kt", "package x\nclass X\n")
    _write(tmp_path / "node_modules" / "Y.ts", "export const y = 1;\n")
    _write(tmp_path / "src" / "B.tsx", "export const B = () => <div/>;\n")
    found = builder.discover_source_files(tmp_path)
    # discover_source_files returns dict keyed by extension (e.g. ".kt", ".tsx").
    all_kt = [str(p) for p in found.get(".kt", []) + found.get(".kts", [])]
    all_ts = [str(p) for p in found.get(".ts", []) + found.get(".tsx", [])]
    assert any("src/A.kt" in p for p in all_kt)
    assert not any("/build/X.kt" in p for p in all_kt)
    assert not any("node_modules" in p for p in all_ts)
    assert any("src/B.tsx" in p for p in all_ts)


def test_infer_feature_slug_returns_segment():
    # Private helper — exercises the regex / split logic that drives feature
    # backfill in build_full.
    fn = getattr(builder, "_infer_feature_slug", None)
    assert fn is not None
    # The helper expects a path under a known feature root.
    slug = fn("shared/feature/auth/domain/Foo.kt")
    assert slug == "auth"


def test_build_full_populates_files_and_symbols(tmp_path):
    project = tmp_path / "proj"
    _write(
        project / "src" / "feature" / "auth" / "AuthViewModel.kt",
        "package com.example.auth\nclass AuthViewModel\n",
    )
    _write(
        project / "src" / "Other.swift",
        "import SwiftUI\nstruct OtherView: View { var body: some View { Text(\"x\") } }\n",
    )
    db = project / "graph.db"
    stats = builder.build_full(project, db_path=db)
    # Stats key is `files_scanned` per the builder.
    assert stats.get("files_scanned", 0) >= 2

    conn = open_db(db, create=False)
    try:
        rows = conn.execute("SELECT path, language FROM files ORDER BY path").fetchall()
        assert any(r["language"] == "kotlin" for r in rows)
        assert any(r["language"] == "swift" for r in rows)
        sym_count = conn.execute("SELECT COUNT(*) AS n FROM symbols").fetchone()["n"]
        assert sym_count >= 2
    finally:
        conn.close()


def test_build_full_is_idempotent(tmp_path):
    project = tmp_path / "p"
    _write(project / "X.kt", "package x\nclass X\n")
    db = project / "graph.db"
    builder.build_full(project, db_path=db)
    builder.build_full(project, db_path=db)
    conn = open_db(db, create=False)
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"]
        assert n == 1
    finally:
        conn.close()
