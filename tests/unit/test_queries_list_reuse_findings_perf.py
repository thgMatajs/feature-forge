"""Performance regression — A13 N+1 collapse in ``list_reuse_findings``.

Pre-fix: 1 query for findings + N queries (one per finding) for locations.
Post-fix: 2 queries total (findings + single IN-clause batch).

This test pins the contract via ``conn.set_trace_callback`` count
instrumentation — guards against regression even if SQL output stays
visually correct.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from engine.graph import queries
from engine.utils.sqlite_io import open_db, transaction


def _seed_reuse_findings(db_path: Path, n_findings: int, locs_per_finding: int) -> None:
    """Insert ``n_findings`` rows + ``locs_per_finding`` locations each.

    Each location references a unique file row — required by the FK.
    """
    conn = open_db(db_path, create=True)
    try:
        with transaction(conn):
            file_ids: list[int] = []
            for i in range(n_findings * locs_per_finding):
                cur = conn.execute(
                    "INSERT INTO files(path, language, module) VALUES (?, ?, ?)",
                    (f"src/file_{i}.kt", "kotlin", f"app:m{i % 3}"),
                )
                file_ids.append(cur.lastrowid)

            for f_idx in range(n_findings):
                cur = conn.execute(
                    """
                    INSERT INTO reuse_findings(
                        category, group_id, symbol_name, receiver_type,
                        canonical_signature, body_hash, primary_language,
                        modifiers, suggested_target, confidence,
                        similarity_score, detected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "duplicate-cross-module",
                        f"grp-{f_idx}",
                        f"sym_{f_idx}",
                        "Receiver",
                        "fun()",
                        "hash" + str(f_idx),
                        "kotlin",
                        "",
                        "shared:core",
                        0.95,
                        1.0,
                        "2026-06-02T00:00:00Z",
                    ),
                )
                finding_id = cur.lastrowid
                for j in range(locs_per_finding):
                    file_id = file_ids[f_idx * locs_per_finding + j]
                    conn.execute(
                        """
                        INSERT INTO reuse_finding_locations(
                            finding_id, file_id, module, source_set,
                            line_start, language, body_hash
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            finding_id,
                            file_id,
                            f"app:m{j}",
                            "main",
                            10 + j,
                            "kotlin",
                            "hash" + str(f_idx),
                        ),
                    )
    finally:
        conn.close()


def test_list_reuse_findings_returns_all_with_locations(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    _seed_reuse_findings(db, n_findings=50, locs_per_finding=3)

    findings = queries.list_reuse_findings(tmp_path, db_path=db)

    assert len(findings) == 50
    for f in findings:
        assert "locations" in f
        assert len(f["locations"]) == 3
        # Each location dict carries the expected shape (no finding_id leak).
        for loc in f["locations"]:
            assert set(loc.keys()) == {
                "module",
                "source_set",
                "line_start",
                "language",
                "body_hash",
                "path",
            }


def test_list_reuse_findings_uses_two_queries_not_n_plus_one(tmp_path: Path) -> None:
    """A13 regression guard — total non-trivial SELECT count must be 2, not 51."""
    db = tmp_path / "g.db"
    _seed_reuse_findings(db, n_findings=50, locs_per_finding=3)

    # Count SELECT executions during the call. We instrument the same
    # connection object the function would otherwise open — monkeypatch
    # the internal ``_connect`` to hand us back an instrumented conn.
    select_count = {"n": 0}

    real_open = open_db

    def _instrumented_connect(_root: Path, db_path):
        conn = real_open(db_path, create=False)

        def _trace(stmt: str) -> None:
            stripped = stmt.lstrip().upper()
            if stripped.startswith("SELECT"):
                select_count["n"] += 1

        conn.set_trace_callback(_trace)
        return conn

    import engine.graph.queries as queries_module

    original = queries_module._connect
    queries_module._connect = _instrumented_connect
    try:
        findings = queries.list_reuse_findings(tmp_path, db_path=db)
    finally:
        queries_module._connect = original

    assert len(findings) == 50, "sanity: function still returns full result"
    # 2 SELECTs: findings + locations batch. Pre-fix would have been 51
    # (1 findings + 50 per-finding location lookups).
    assert select_count["n"] == 2, (
        f"expected 2 SELECTs (findings + IN-clause batch), got {select_count['n']}"
    )


def test_list_reuse_findings_empty_returns_early(tmp_path: Path) -> None:
    """No findings → no location query fired (empty IN clause would be invalid)."""
    db = tmp_path / "g.db"
    # Create empty schema only.
    conn = open_db(db, create=True)
    conn.close()

    result = queries.list_reuse_findings(tmp_path, db_path=db)
    assert result == []
