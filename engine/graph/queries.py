"""Canonical named queries Q1–Q10 backing the `forge graph` menu.

Every query opens a short-lived read-only-ish connection (WAL allows
concurrent readers with writers), runs SQL, and returns plain Python dicts /
lists sorted by stable keys so output is deterministic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from engine.utils.paths import graph_db_path
from engine.utils.sqlite_io import open_db


def _connect(project_root: Path, db_path: Optional[Path]) -> sqlite3.Connection:
    target = db_path or graph_db_path(project_root)
    return open_db(target, create=False)


def find_similar_features(
    project_root: Path,
    feature_slug: str,
    *,
    top_n: int = 5,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q2 — features structurally similar to the target slug.

    Ranking heuristic: absolute delta between screen counts.
    """
    conn = _connect(project_root, db_path)
    try:
        target_screens_row = conn.execute(
            "SELECT COUNT(*) AS n FROM screens WHERE feature_slug = ?",
            (feature_slug,),
        ).fetchone()
        target_screens = target_screens_row["n"] if target_screens_row else 0

        rows = conn.execute(
            """
            SELECT f.slug, f.status,
                   (SELECT COUNT(*) FROM screens s WHERE s.feature_slug = f.slug) AS screens
            FROM features f
            WHERE f.slug != ?
            """,
            (feature_slug,),
        ).fetchall()
        scored = [
            {
                "slug": row["slug"],
                "status": row["status"],
                "screens": row["screens"],
                "delta": abs(row["screens"] - target_screens),
            }
            for row in rows
        ]
        scored.sort(key=lambda item: (item["delta"], item["slug"]))
        return scored[:top_n]
    finally:
        conn.close()


def blast_radius(
    project_root: Path,
    file_paths: list[Path],
    *,
    db_path: Optional[Path] = None,
) -> dict:
    """Q3 — files (and features) impacted if the given files change.

    Resolves by symbol name proxy: takes symbols defined in those files,
    then finds importers pointing at any of those symbols.
    """
    conn = _connect(project_root, db_path)
    try:
        rel_paths = sorted({str(p) for p in file_paths})
        if not rel_paths:
            return {"impacted_files": [], "impacted_features": []}

        placeholders = ",".join("?" for _ in rel_paths)
        symbols = conn.execute(
            f"""
            SELECT DISTINCT s.name
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE f.path IN ({placeholders})
            """,
            rel_paths,
        ).fetchall()
        symbol_names = sorted({row["name"] for row in symbols})

        # Batch: 1 query OR'd com LIKE por símbolo em vez de 1 query por símbolo.
        # Evita N+1 — change touching 5 files × 50 symbols ia executar 250 queries antes.
        impacted_files: set[str] = set()
        if symbol_names:
            like_clauses = " OR ".join("i.to_symbol LIKE ?" for _ in symbol_names)
            like_params = [f"%{name}%" for name in symbol_names]
            rows = conn.execute(
                f"""
                SELECT DISTINCT f.path
                FROM imports i
                JOIN files f ON i.from_file_id = f.id
                WHERE {like_clauses}
                """,
                like_params,
            ).fetchall()
            impacted_files.update(row["path"] for row in rows)
        impacted_files.difference_update(rel_paths)

        feature_rows = conn.execute(
            """
            SELECT DISTINCT s.feature_slug
            FROM screens s
            JOIN files f ON s.file_id = f.id
            WHERE f.path IN ({})
            """.format(placeholders),
            rel_paths,
        ).fetchall()
        impacted_features = sorted({row["feature_slug"] for row in feature_rows})

        return {
            "impacted_files": sorted(impacted_files),
            "impacted_features": impacted_features,
            "via_symbols": symbol_names,
        }
    finally:
        conn.close()


def find_orphan_files(
    project_root: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[Path]:
    """Q (variant) — files whose declared symbols are never imported elsewhere.

    F8: o LIKE anterior (`'%' || s.name`) era largo demais — `s.name = "Foo"`
    casava com qualquer to_symbol terminando em `Foo` (incluindo `BarFoo`,
    `MyFoo`). Agora exigimos boundary explícita: match exato OU prefixado
    por ponto (qualificado por package).
    """
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT f.path
            FROM files f
            WHERE NOT EXISTS (
              SELECT 1
              FROM symbols s
              JOIN imports i
                ON i.to_symbol = s.name OR i.to_symbol LIKE '%.' || s.name
              WHERE s.file_id = f.id AND i.from_file_id != f.id
            )
            ORDER BY f.path
            """
        ).fetchall()
        return [Path(row["path"]) for row in rows]
    finally:
        conn.close()


def find_symbols_in_module(
    project_root: Path,
    module_name: str,
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q4 — every symbol defined inside files belonging to a Gradle module."""
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT s.name, s.kind, s.visibility, f.path, s.line_start
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE f.module = ?
            ORDER BY f.path, s.line_start, s.name
            """,
            (module_name,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def find_ds_components_used_in(
    project_root: Path,
    feature_slug: str,
    *,
    db_path: Optional[Path] = None,
) -> list[str]:
    """Q5 — design-system component names referenced by a feature's screens."""
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT c.name
            FROM ds_usage u
            JOIN ds_components c ON u.component_id = c.id
            JOIN screens s ON u.screen_id = s.id
            WHERE s.feature_slug = ?
            ORDER BY c.name
            """,
            (feature_slug,),
        ).fetchall()
        return [row["name"] for row in rows]
    finally:
        conn.close()


def find_i18n_keys_used_in(
    project_root: Path,
    feature_slug: str,
    *,
    db_path: Optional[Path] = None,
) -> list[str]:
    """Q6 — i18n keys consumed by files attached to a feature's screens."""
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT k.key
            FROM i18n_usage u
            JOIN i18n_keys k ON u.key_id = k.id
            JOIN screens s ON s.file_id = u.file_id
            WHERE s.feature_slug = ?
            ORDER BY k.key
            """,
            (feature_slug,),
        ).fetchall()
        return [row["key"] for row in rows]
    finally:
        conn.close()


def find_routes_in_feature(
    project_root: Path,
    feature_slug: str,
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q7 — navigable routes belonging to a feature (via screens)."""
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT r.key, r.type, r.params_json
            FROM routes r
            JOIN screens s ON s.route_id = r.id
            WHERE s.feature_slug = ?
            ORDER BY r.key
            """,
            (feature_slug,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def find_di_dependencies(
    project_root: Path,
    class_name: str,
    *,
    db_path: Optional[Path] = None,
) -> dict:
    """Q8 — DI providers / consumers anchored at a given class name."""
    conn = _connect(project_root, db_path)
    try:
        provided_by = conn.execute(
            """
            SELECT DISTINCT s_provider.name AS provider, d.scope, d.kind
            FROM di_graph d
            JOIN symbols s_consumer ON s_consumer.id = d.consumer_symbol_id
            JOIN symbols s_provider ON s_provider.id = d.provider_symbol_id
            WHERE s_consumer.name = ?
            ORDER BY provider
            """,
            (class_name,),
        ).fetchall()
        consumed_by = conn.execute(
            """
            SELECT DISTINCT s_consumer.name AS consumer, d.scope, d.kind
            FROM di_graph d
            JOIN symbols s_provider ON s_provider.id = d.provider_symbol_id
            JOIN symbols s_consumer ON s_consumer.id = d.consumer_symbol_id
            WHERE s_provider.name = ?
            ORDER BY consumer
            """,
            (class_name,),
        ).fetchall()
        return {
            "class": class_name,
            "provided_by": [dict(row) for row in provided_by],
            "consumed_by": [dict(row) for row in consumed_by],
        }
    finally:
        conn.close()


def find_tests_covering_file(
    project_root: Path,
    file_path: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[Path]:
    """Q9 — test files whose `target_file_id` points at this production file."""
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT f_test.path AS test_path
            FROM tests t
            JOIN files f_test ON t.file_id = f_test.id
            JOIN files f_target ON t.target_file_id = f_target.id
            WHERE f_target.path = ?
            ORDER BY f_test.path
            """,
            (str(file_path),),
        ).fetchall()
        return [Path(row["test_path"]) for row in rows]
    finally:
        conn.close()


def commits_touching_feature(
    project_root: Path,
    feature_slug: str,
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q10 — commits associated with a feature (or any of its tasks)."""
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT commit_sha, timestamp, files_touched_count, source
            FROM (
              SELECT commit_sha, timestamp, files_touched_count, 'feature' AS source
              FROM feature_commits
              WHERE feature_slug = ?
              UNION ALL
              SELECT commit_sha, timestamp, files_touched_count, 'task' AS source
              FROM task_commits
              WHERE task_id LIKE ? || ':%'
            )
            ORDER BY timestamp DESC, commit_sha
            """,
            (feature_slug, feature_slug),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
