"""Integration test — graph builder against MeoBonsai.

Skipped when MeoBonsai is not available locally. Builds a graph DB in a
tmp_path and asserts that core tables are populated with non-trivial counts.

Time budget: <30s for the typical MeoBonsai snapshot. Marked `integration`
so rapid CI lanes can skip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.graph import builder
from engine.utils.sqlite_io import open_db


@pytest.mark.integration
def test_build_full_meobonsai(meobonsai_root, tmp_path):
    db = tmp_path / "graph.db"
    stats = builder.build_full(meobonsai_root, db_path=db)
    assert stats.get("files_scanned", 0) > 0

    conn = open_db(db, create=False)
    try:
        files = conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"]
        symbols = conn.execute("SELECT COUNT(*) AS n FROM symbols").fetchone()["n"]
        assert files >= 10
        assert symbols >= 10
        # MeoBonsai has both Kotlin and Swift files.
        langs = {
            row["language"]
            for row in conn.execute("SELECT DISTINCT language FROM files").fetchall()
            if row["language"]
        }
        assert "kotlin" in langs
    finally:
        conn.close()


@pytest.mark.integration
def test_build_full_creates_meta_schema_version(meobonsai_root, tmp_path):
    db = tmp_path / "graph.db"
    builder.build_full(meobonsai_root, db_path=db)
    conn = open_db(db, create=False)
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        assert row is not None
        assert row["value"] == "1"
    finally:
        conn.close()


@pytest.mark.integration
def test_discover_source_files_meobonsai_includes_kotlin(meobonsai_root):
    found = builder.discover_source_files(meobonsai_root)
    # discover_source_files returns dict keyed by extension (e.g. ".kt").
    all_kt = found.get(".kt", []) + found.get(".kts", [])
    assert len(all_kt) > 0
