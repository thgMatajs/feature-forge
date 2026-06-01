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


# ── Q11 — find_reusable_helpers ─────────────────────────────────────────────


def _seed_reusable_helpers(db_path: Path) -> None:
    """Seed with utility helpers in `shared` module for Q11 tests.

    Mix of: util-path helper, extension referencing a domain entity, a
    helper in a non-utility path that doesn't reference any entity (should
    NOT be returned), a private helper (filtered out), and a class (filtered
    by kind='fun').
    """
    conn = open_db(db_path, create=True)
    try:
        with transaction(conn):
            conn.executemany(
                "INSERT INTO files(path, language, module) VALUES (?, ?, ?)",
                [
                    ("shared/core/util/StringDateExtension.kt", "kotlin", "shared"),
                    ("shared/feature/bonsai/util/BonsaiFormatter.kt", "kotlin", "shared"),
                    ("shared/feature/bonsai/data/BonsaiRepositoryImpl.kt", "kotlin", "shared"),
                    ("shared/core/util/ResultExtension.kt", "kotlin", "shared"),
                    ("androidApp/feature/bonsai/BonsaiScreen.kt", "kotlin", "androidApp"),
                ],
            )
            file_ids = {
                row["path"]: row["id"]
                for row in conn.execute("SELECT id, path FROM files").fetchall()
            }
            conn.executemany(
                "INSERT INTO symbols(file_id, name, kind, signature, visibility, line_start) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    # General-purpose stdlib helper in util path — should match
                    (
                        file_ids["shared/core/util/StringDateExtension.kt"],
                        "toLocalDateOrNull",
                        "fun",
                        "fun String.toLocalDateOrNull(): LocalDate?",
                        "public",
                        10,
                    ),
                    # Extension referencing Bonsai entity — should match on entity
                    (
                        file_ids["shared/feature/bonsai/util/BonsaiFormatter.kt"],
                        "formatDisplay",
                        "fun",
                        "fun Bonsai.formatDisplay(): String",
                        "public",
                        15,
                    ),
                    # Repository impl class — filtered by kind='fun'
                    (
                        file_ids["shared/feature/bonsai/data/BonsaiRepositoryImpl.kt"],
                        "BonsaiRepositoryImpl",
                        "class",
                        "class BonsaiRepositoryImpl(...)",
                        "public",
                        5,
                    ),
                    # Public fun in util path — should match
                    (
                        file_ids["shared/core/util/ResultExtension.kt"],
                        "foldStateUI",
                        "fun",
                        "fun <T> Result<T>.foldStateUI(): StateUI<T>",
                        "public",
                        20,
                    ),
                    # Private fun — filtered by visibility
                    (
                        file_ids["shared/core/util/ResultExtension.kt"],
                        "internalHelper",
                        "fun",
                        "private fun helper(): Unit",
                        "private",
                        40,
                    ),
                    # androidApp module — filtered by module='shared'
                    (
                        file_ids["androidApp/feature/bonsai/BonsaiScreen.kt"],
                        "renderBonsai",
                        "fun",
                        "fun renderBonsai(b: Bonsai): Unit",
                        "public",
                        30,
                    ),
                ],
            )
    finally:
        conn.close()


def test_find_reusable_helpers_matches_entity_types(tmp_path):
    db = tmp_path / "g.db"
    _seed_reusable_helpers(db)
    rows = queries.find_reusable_helpers(tmp_path, ["Bonsai"], db_path=db)
    names = [r["name"] for r in rows]
    # Bonsai.formatDisplay extension matches signature; foldStateUI and
    # toLocalDateOrNull match utility-path; BonsaiRepositoryImpl excluded
    # (kind=class); renderBonsai excluded (module=androidApp).
    assert "formatDisplay" in names
    assert "BonsaiRepositoryImpl" not in names
    assert "renderBonsai" not in names
    # Relevance is the entity match when signature contains it
    fmt = next(r for r in rows if r["name"] == "formatDisplay")
    assert fmt["relevance"] == "signature-references-Bonsai"


def test_find_reusable_helpers_filters_visibility_and_module(tmp_path):
    db = tmp_path / "g.db"
    _seed_reusable_helpers(db)
    rows = queries.find_reusable_helpers(tmp_path, [], db_path=db)
    # Private fun is excluded, androidApp module is excluded, classes excluded
    names = [r["name"] for r in rows]
    assert "internalHelper" not in names
    assert "renderBonsai" not in names
    assert "BonsaiRepositoryImpl" not in names
    # Utility helpers all present even with empty entity list
    assert "toLocalDateOrNull" in names
    assert "foldStateUI" in names


def test_find_reusable_helpers_empty_inputs_returns_empty(tmp_path):
    """Empty entity types + empty path fragments → empty result (defensive)."""
    db = tmp_path / "g.db"
    _seed_reusable_helpers(db)
    rows = queries.find_reusable_helpers(
        tmp_path, [], util_path_fragments=[], db_path=db
    )
    assert rows == []
