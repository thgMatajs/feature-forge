"""Unit tests — engine.graph.queries.

Pre-populates a temporary graph DB with rows directly, then asserts that the
canonical queries (Q1–Q3 subset) return deterministic results sorted by
stable keys.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.utils.sqlite_io import open_db, transaction


def _seed_db(db_path: Path) -> None:
    conn = open_db(db_path, create=True)
    try:
        with transaction(conn):
            conn.executemany(
                "INSERT INTO files(path, language, module) VALUES (?, ?, ?)",
                [
                    ("shared/auth/AuthVM.kt", "kotlin", "shared:auth"),
                    ("shared/bonsai/BonsaiVM.kt", "kotlin", "shared:bonsai"),
                    ("ios/Auth/LoginView.swift", "swift", "ios:auth"),
                ],
            )
            conn.executemany(
                "INSERT INTO features(slug, status) VALUES (?, ?)",
                [
                    ("auth", "done"),
                    ("bonsai", "planning"),
                    ("water-reminder", "planned"),
                ],
            )
            # screens — variable counts per feature for similarity ranking.
            file_ids = {
                r["path"]: r["id"]
                for r in conn.execute("SELECT id, path FROM files").fetchall()
            }
            conn.executemany(
                "INSERT INTO screens(feature_slug, name, file_id) VALUES (?, ?, ?)",
                [
                    ("auth", "LoginScreen", file_ids["shared/auth/AuthVM.kt"]),
                    ("auth", "RegisterScreen", file_ids["shared/auth/AuthVM.kt"]),
                    ("bonsai", "DetailScreen", file_ids["shared/bonsai/BonsaiVM.kt"]),
                ],
            )
    finally:
        conn.close()


def test_find_similar_features_ranks_by_delta(tmp_path):
    db = tmp_path / "g.db"
    _seed_db(db)
    sim = queries.find_similar_features(tmp_path, "bonsai", db_path=db)
    # bonsai has 1 screen; auth has 2 (delta=1), water-reminder has 0 (delta=1).
    assert sim
    # Both have delta=1 — alphabetical tiebreak (auth before water-reminder).
    deltas = [item["delta"] for item in sim]
    assert deltas == sorted(deltas)
    if len(sim) >= 2 and sim[0]["delta"] == sim[1]["delta"]:
        assert sim[0]["slug"] < sim[1]["slug"]


def test_find_similar_features_excludes_target(tmp_path):
    db = tmp_path / "g.db"
    _seed_db(db)
    sim = queries.find_similar_features(tmp_path, "auth", db_path=db)
    assert all(item["slug"] != "auth" for item in sim)


def test_find_symbols_in_module(tmp_path):
    db = tmp_path / "g.db"
    _seed_db(db)
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            row = conn.execute(
                "SELECT id FROM files WHERE path = ?", ("shared/auth/AuthVM.kt",)
            ).fetchone()
            file_id = row["id"]
            conn.execute(
                "INSERT INTO symbols(file_id, name, kind, line_start) VALUES (?, ?, ?, ?)",
                (file_id, "AuthViewModel", "class", 1),
            )
    finally:
        conn.close()

    found = queries.find_symbols_in_module(tmp_path, "shared:auth", db_path=db)
    names = [s["name"] for s in found]
    assert "AuthViewModel" in names


def test_blast_radius_returns_dict_shape(tmp_path):
    db = tmp_path / "g.db"
    _seed_db(db)
    result = queries.blast_radius(tmp_path, [Path("shared/auth/AuthVM.kt")], db_path=db)
    assert isinstance(result, dict)
