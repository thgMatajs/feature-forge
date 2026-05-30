"""Incremental graph updates — re-parse a single file (or a batch) and
swap symbols/imports/i18n_usage/ds_usage rows in place.

Invoked by `forge ingest` from post-edit/post-commit hooks. Latency budget per
file: 50-200ms.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from engine.graph.builder import (
    _LANGUAGE_EXTENSIONS,
    _ensure_imports_to_file_id_column,
    _infer_feature_slug,
    _infer_module,
    _infer_test_framework,
    _infer_test_target_file_id,
    _persist_kotlin,
    _persist_swift,
    _persist_typescript,
    _relpath,
    _resolve_import_targets,
    _screen_name_from_path,
)
from engine.graph.parser_kotlin import parse_kotlin_file
from engine.graph.parser_swift import parse_swift_file
from engine.graph.parser_typescript import parse_typescript_file
from engine.utils.paths import graph_db_path
from engine.utils.sqlite_io import open_db, transaction


def update_file(
    project_root: Path,
    file_path: Path,
    *,
    db_path: Optional[Path] = None,
) -> dict:
    """Re-parse a single file and refresh its edges/symbols."""
    target_db = db_path or graph_db_path(project_root)
    conn = open_db(target_db, create=True)
    try:
        _ensure_imports_to_file_id_column(conn)
        with transaction(conn):
            stats = _refresh_file(conn, project_root, file_path)
            _resolve_import_targets(conn)
        return stats
    finally:
        conn.close()


def remove_file(
    project_root: Path,
    file_path: Path,
    *,
    db_path: Optional[Path] = None,
) -> dict:
    """Remove all symbols/edges originating from this file."""
    target_db = db_path or graph_db_path(project_root)
    conn = open_db(target_db, create=True)
    try:
        _ensure_imports_to_file_id_column(conn)
        rel = _relpath(project_root, file_path)
        with transaction(conn):
            file_id = _file_id(conn, rel)
            if file_id is None:
                return {"removed": False, "file_id": None}
            _purge_file_rows(conn, file_id)
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        return {"removed": True, "file_id": file_id, "path": rel}
    finally:
        conn.close()


def update_batch(
    project_root: Path,
    file_paths: list[Path],
    *,
    db_path: Optional[Path] = None,
) -> dict:
    """Refresh many files inside a single transaction."""
    target_db = db_path or graph_db_path(project_root)
    conn = open_db(target_db, create=True)
    try:
        _ensure_imports_to_file_id_column(conn)
        files_updated = 0
        symbols_total = 0
        edges_total = 0
        with transaction(conn):
            for file_path in file_paths:
                if not file_path.exists():
                    rel = _relpath(project_root, file_path)
                    file_id = _file_id(conn, rel)
                    if file_id is not None:
                        _purge_file_rows(conn, file_id)
                        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
                    continue
                stats = _refresh_file(conn, project_root, file_path)
                files_updated += 1
                symbols_total += stats.get("symbols", 0)
                edges_total += stats.get("edges", 0)
            _resolve_import_targets(conn)
        return {
            "files_updated": files_updated,
            "symbols": symbols_total,
            "edges": edges_total,
        }
    finally:
        conn.close()


def _refresh_file(
    conn: sqlite3.Connection,
    project_root: Path,
    file_path: Path,
) -> dict:
    ext = file_path.suffix.lower()
    if ext not in _LANGUAGE_EXTENSIONS:
        return {"symbols": 0, "edges": 0, "skipped": True}

    language = _LANGUAGE_EXTENSIONS[ext]
    rel = _relpath(project_root, file_path)
    module = _infer_module(rel)

    try:
        raw = file_path.read_bytes()
    except OSError:
        return {"symbols": 0, "edges": 0, "skipped": True}

    sha256 = hashlib.sha256(raw).hexdigest()
    line_count = raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1)
    last_modified = datetime.fromtimestamp(
        file_path.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    conn.execute(
        "INSERT INTO files(path, language, module, lines, last_modified, sha256) "
        "VALUES(?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET "
        "  language=excluded.language, module=excluded.module, "
        "  lines=excluded.lines, last_modified=excluded.last_modified, "
        "  sha256=excluded.sha256",
        (rel, language, module, line_count, last_modified, sha256),
    )
    file_id = _file_id(conn, rel)
    if file_id is None:
        return {"symbols": 0, "edges": 0, "skipped": True}

    _purge_file_rows(conn, file_id)

    if language == "kotlin":
        info = parse_kotlin_file(file_path)
        stats = _persist_kotlin(conn, file_id, info)
    elif language == "swift":
        info_sw = parse_swift_file(file_path)
        stats = _persist_swift(conn, file_id, info_sw)
    elif language in {"typescript", "javascript"}:
        info_ts = parse_typescript_file(file_path)
        stats = _persist_typescript(conn, file_id, info_ts)
    else:
        return {"symbols": 0, "edges": 0}

    _refresh_file_post_pass(conn, file_id, rel, language)
    return stats


def _refresh_file_post_pass(
    conn: sqlite3.Connection,
    file_id: int,
    rel: str,
    language: Optional[str],
) -> None:
    """Re-derive ds_usage / screens / routes / tests rows for this single file."""
    components = conn.execute("SELECT id, name FROM ds_components").fetchall()
    for comp in components:
        comp_id = comp["id"]
        comp_name = comp["name"]
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM imports "
            "WHERE from_file_id = ? AND (to_symbol = ? OR to_symbol LIKE ?)",
            (file_id, comp_name, f"%.{comp_name}"),
        ).fetchone()
        if row and row["n"] > 0:
            conn.execute(
                "INSERT INTO ds_usage(component_id, screen_id, file_id, occurrences) "
                "VALUES(?, NULL, ?, ?)",
                (comp_id, file_id, row["n"]),
            )

    if (
        rel.endswith("Screen.kt")
        or rel.endswith("ScreenView.swift")
        or rel.endswith("Page.tsx")
        or rel.endswith("Page.jsx")
    ):
        feature_slug = _infer_feature_slug(rel)
        if feature_slug is not None:
            conn.execute(
                "INSERT OR IGNORE INTO features(slug, status, created_at, last_activity, modules) "
                "VALUES(?, 'detected', NULL, NULL, NULL)",
                (feature_slug,),
            )
            conn.execute(
                "INSERT INTO screens(feature_slug, name, file_id, route_id) VALUES(?, ?, ?, NULL)",
                (feature_slug, _screen_name_from_path(rel), file_id),
            )

    route_symbols = conn.execute(
        "SELECT name, kind FROM symbols "
        "WHERE file_id = ? AND (name LIKE '%Route' OR name = 'AppRoute' OR kind = 'sealed_class')",
        (file_id,),
    ).fetchall()
    for row in route_symbols:
        conn.execute(
            "INSERT OR IGNORE INTO routes(key, params_json, type, defined_in_file) "
            "VALUES(?, NULL, ?, ?)",
            (row["name"], row["kind"], file_id),
        )

    lower = rel.lower()
    is_test = (
        rel.endswith("Test.kt")
        or rel.endswith("Tests.swift")
        or lower.endswith(".test.ts")
        or lower.endswith(".test.tsx")
        or lower.endswith(".spec.ts")
        or lower.endswith(".spec.tsx")
    )
    if is_test:
        framework = _infer_test_framework(rel, language)
        target_id = _infer_test_target_file_id(conn, rel)
        conn.execute(
            "INSERT INTO tests(file_id, target_file_id, kind, status) VALUES(?, ?, ?, 'unknown')",
            (file_id, target_id, framework),
        )


def _file_id(conn: sqlite3.Connection, rel_path: str) -> Optional[int]:
    row = conn.execute("SELECT id FROM files WHERE path = ?", (rel_path,)).fetchone()
    return row["id"] if row else None


def _purge_file_rows(conn: sqlite3.Connection, file_id: int) -> None:
    """Wipe everything derived from this file before re-inserting."""
    conn.execute("DELETE FROM imports WHERE from_file_id = ?", (file_id,))
    conn.execute("DELETE FROM i18n_usage WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM ds_usage WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM tests WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM screens WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM routes WHERE defined_in_file = ?", (file_id,))
    conn.execute(
        "DELETE FROM di_graph WHERE provider_symbol_id IN "
        "(SELECT id FROM symbols WHERE file_id = ?)",
        (file_id,),
    )
    conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
