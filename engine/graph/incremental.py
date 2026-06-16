"""Incremental graph updates — re-parse a single file (or a batch) and
swap symbols/imports/i18n_usage/ds_usage rows in place.

Invoked by `forge ingest` from post-edit/post-commit hooks. Latency budget per
file: 50-200ms.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("engine.graph.incremental")

from engine.graph.builder import (
    _LANGUAGE_EXTENSIONS,
    _ensure_graph_body_column,
    _ensure_imports_to_file_id_column,
    _ensure_reuse_intelligence_columns,
    _infer_feature_slug,
    _infer_test_framework,
    _infer_test_target_file_id,
    _persist_java,
    _persist_kotlin,
    _persist_objc,
    _persist_swift,
    _persist_typescript,
    _persist_xml,
    _relpath,
    _resolve_import_targets,
    _screen_name_from_path,
)
from engine.graph.gradle_modules import (
    infer_module_and_source_set,
    load_gradle_modules,
)
from engine.graph.parser_java import parse_java_file
from engine.graph.parser_kotlin import parse_kotlin_file
from engine.graph.parser_objc import parse_objc_file
from engine.graph.parser_swift import parse_swift_file
from engine.graph.parser_typescript import parse_typescript_file
from engine.graph.parser_xml import parse_xml_file
from engine.utils.paths import graph_db_path
from engine.utils.sqlite_io import open_db, transaction


# M-008: caching marker pra evitar re-rodar os 3 ``_ensure_*`` em todo
# entrypoint do hook. Os ``_ensure_*`` são idempotentes mas executam
# múltiplas queries de introspecção (PRAGMA table_info) por chamada —
# isso virava overhead linear em batches grandes. Marker fica em ``meta``
# (canonical key/value table), persistido entre invocações.
_MIGRATIONS_KEY = "migrations_applied_v1_3"


def _migrations_applied(conn: sqlite3.Connection) -> bool:
    """Check if ``_ensure_*`` migrations já rodaram nesta DB."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (_MIGRATIONS_KEY,)
        ).fetchone()
    except sqlite3.OperationalError:
        # ``meta`` table ainda não existe (DB pré-init_schema). Fall-through
        # pra rodar _ensure_* — quem chama é open_db(create=True), então
        # meta vai existir após. Conservador: retorna False.
        return False
    return row is not None and row["value"] == "1"


def _mark_migrations_applied(conn: sqlite3.Connection) -> None:
    """Persiste marker pra próxima invocação pular os ``_ensure_*``.

    Usa ``INSERT OR REPLACE`` (UPSERT) pra ser idempotente sob race:
    se 2 hooks rodam concorrente e ambos chegam aqui, ambos escrevem
    o mesmo valor sem conflito.
    """
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, '1')",
        (_MIGRATIONS_KEY,),
    )


def _apply_ensure_migrations(conn: sqlite3.Connection) -> None:
    """Run the 3 ``_ensure_*`` calls once, then stamp the marker.

    Helper consolidando o padrão repetido em update_file/remove_file/
    update_batch. Idempotente por design — cada ``_ensure_*`` é safe
    pra chamar várias vezes, e o marker apenas pula o overhead.

    E-N-003 (master review PR #16): TOCTOU race window. Process A le
    marker → ausente → começa ALTER TABLE; process B le marker → ainda
    ausente → começa ALTER TABLE → SQLite raise ``OperationalError(
    "duplicate column name")`` porque A já adicionou. Tratamos como
    idempotência (mensagem específica engole; outras razões re-raise
    pra preservar telemetria). Hook bash mascara via ``2>&1 || true``,
    mas chamadas diretas (test, REPL, futuro CLI sub-comando) precisam
    do fix.
    """
    if _migrations_applied(conn):
        return
    try:
        _ensure_imports_to_file_id_column(conn)
        _ensure_reuse_intelligence_columns(conn)
        _ensure_graph_body_column(conn)
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "duplicate column name" in msg:
            _logger.debug(
                "concurrent migration detected (race window swallowed): %s",
                exc,
            )
        else:
            _logger.error(
                "incremental migration failed (not TOCTOU race): %s",
                exc,
                exc_info=True,
            )
            raise
    _mark_migrations_applied(conn)


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
        gradle_modules = load_gradle_modules(project_root)
        _apply_ensure_migrations(conn)
        with transaction(conn):
            stats = _refresh_file(conn, project_root, file_path, gradle_modules)
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
        _apply_ensure_migrations(conn)
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
    """Refresh many files inside a single transaction.

    Per-file error handling (codereviewbot incremental.py:155): falhas
    individuais em ``_file_id`` / ``_purge_file_rows`` / ``DELETE`` /
    ``_refresh_file`` são logadas via logger.warning e contadas em
    ``files_failed`` mas NÃO abortam o batch — estado parcial é OK pra
    hook context (best-effort), e o transaction context manager segura
    rollback do que estava em vôo via raise indireto.

    N-008: stats agora retorna ``files_processed`` (covering update +
    delete) além de ``files_updated`` (apenas refresh). ``files_failed``
    e ``files_deleted`` ficam visíveis pra audit downstream.
    """
    target_db = db_path or graph_db_path(project_root)
    conn = open_db(target_db, create=True)
    try:
        gradle_modules = load_gradle_modules(project_root)
        _apply_ensure_migrations(conn)
        files_updated = 0
        files_deleted = 0
        files_failed = 0
        symbols_total = 0
        edges_total = 0
        with transaction(conn):
            for file_path in file_paths:
                try:
                    if not file_path.exists():
                        rel = _relpath(project_root, file_path)
                        file_id = _file_id(conn, rel)
                        if file_id is not None:
                            _purge_file_rows(conn, file_id)
                            conn.execute(
                                "DELETE FROM files WHERE id = ?", (file_id,)
                            )
                            files_deleted += 1
                        continue
                    stats = _refresh_file(
                        conn, project_root, file_path, gradle_modules
                    )
                    files_updated += 1
                    symbols_total += stats.get("symbols", 0)
                    edges_total += stats.get("edges", 0)
                except Exception as exc:  # noqa: BLE001 — best-effort hook context
                    # Log per-file; não aborta o batch. Mantém o resto do
                    # batch processável; status agregado refletido em
                    # files_failed pra downstream audit.
                    _logger.warning(
                        "update_batch: file %s failed (%s) — continuing batch",
                        file_path,
                        exc,
                    )
                    files_failed += 1
            _resolve_import_targets(conn)
        return {
            "files_updated": files_updated,
            "files_deleted": files_deleted,
            "files_failed": files_failed,
            "files_processed": files_updated + files_deleted,
            "symbols": symbols_total,
            "edges": edges_total,
        }
    finally:
        conn.close()


def detect_after_update(
    project_root: Path,
    file_paths: list[Path],
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Re-parse files + re-run reuse-intelligence detection, return new findings.

    Intended for the post-edit hook: a developer just saved one or more files
    and we want to surface — inline in the terminal — any duplicate /
    cross-module / KMP-migration candidate the edit just introduced (or that
    the edit is now part of).

    Returns a list of finding dicts (one per category match) limited to
    findings whose locations include the edited files. Empty list means the
    edits did not surface new duplications.

    Best-effort: any error returns an empty list so the hook never breaks the
    developer's workflow.
    """
    try:
        from engine.graph.duplicates import detect_all_reuse_findings
        from engine.graph.gradle_deps import parse_module_dependencies
    except ImportError:
        return []

    target_db = db_path or graph_db_path(project_root)
    if not target_db.exists():
        return []

    try:
        update_batch(project_root, file_paths, db_path=target_db)
    except Exception:
        return []

    edited_relpaths = {_relpath(project_root, p) for p in file_paths if p.exists()}

    conn = open_db(target_db, create=False)
    try:
        # Discovery happens INSIDE the try so a failure in either call still
        # closes the connection (R2.5). detect_after_update is best-effort —
        # any error degrades to [] without leaking sqlite handles.
        try:
            gradle_modules = load_gradle_modules(project_root)
            deps = parse_module_dependencies(project_root, gradle_modules)
        except Exception:
            return []
        with transaction(conn):
            detect_all_reuse_findings(conn, gradle_modules, deps)
        if not edited_relpaths:
            return []
        placeholders = ",".join("?" for _ in edited_relpaths)
        rows = conn.execute(
            f"""
            SELECT DISTINCT rf.id, rf.category, rf.symbol_name, rf.receiver_type,
                   rf.suggested_target, rf.confidence, rf.group_id
            FROM reuse_findings rf
            JOIN reuse_finding_locations loc ON loc.finding_id = rf.id
            JOIN files f ON loc.file_id = f.id
            WHERE f.path IN ({placeholders})
            ORDER BY rf.confidence DESC, rf.category
            """,
            list(edited_relpaths),
        ).fetchall()
        results: list[dict] = []
        for row in rows:
            locations = conn.execute(
                """
                SELECT files.path, loc.module, loc.source_set, loc.line_start, loc.language
                FROM reuse_finding_locations loc
                JOIN files ON files.id = loc.file_id
                WHERE loc.finding_id = ?
                ORDER BY loc.module, loc.line_start
                """,
                (row["id"],),
            ).fetchall()
            results.append({
                "id": row["id"],
                "category": row["category"],
                "symbol_name": row["symbol_name"],
                "receiver_type": row["receiver_type"],
                "suggested_target": row["suggested_target"],
                "confidence": row["confidence"],
                "group_id": row["group_id"],
                "locations": [dict(loc) for loc in locations],
            })
        return results
    finally:
        conn.close()


def _refresh_file(
    conn: sqlite3.Connection,
    project_root: Path,
    file_path: Path,
    gradle_modules: Optional[dict[str, str]] = None,
) -> dict:
    ext = file_path.suffix.lower()
    if ext not in _LANGUAGE_EXTENSIONS:
        return {"symbols": 0, "edges": 0, "skipped": True}

    language = _LANGUAGE_EXTENSIONS[ext]
    rel = _relpath(project_root, file_path)
    module, source_set = infer_module_and_source_set(rel, gradle_modules or {})

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
        "INSERT INTO files(path, language, module, source_set, lines, last_modified, sha256) "
        "VALUES(?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET "
        "  language=excluded.language, module=excluded.module, "
        "  source_set=excluded.source_set, "
        "  lines=excluded.lines, last_modified=excluded.last_modified, "
        "  sha256=excluded.sha256",
        (rel, language, module, source_set, line_count, last_modified, sha256),
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
    elif language == "java":
        info_java = parse_java_file(file_path)
        stats = _persist_java(conn, file_id, info_java)
    elif language == "xml":
        info_xml = parse_xml_file(file_path)
        stats = _persist_xml(conn, file_id, info_xml)
    elif language == "objc":
        info_objc = parse_objc_file(file_path)
        stats = _persist_objc(conn, file_id, info_objc)
    else:
        # Unsupported language — language string veio do dict
        # ``_LANGUAGE_EXTENSIONS`` em builder.py mas sem branch
        # correspondente aqui. Codereviewbot incremental.py:331:
        # silent return mascarava drift entre o registry (builder.py)
        # e o dispatch (incremental.py). Log warn + retorno marcado
        # com ``unsupported`` pra audit downstream — não raise (best-
        # effort hook context).
        _logger.warning(
            "_refresh_file: unsupported language=%r for %s — "
            "registry/dispatch drift?",
            language,
            file_path,
        )
        return {"symbols": 0, "edges": 0, "unsupported": True}

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
    """Wipe everything derived from this file before re-inserting.

    Cobre TODAS as tabelas derivadas, incluindo ``reuse_finding_locations``
    (apontava pra ``file_id`` via FK mas era esquecida no purge — agora
    incremental update gerava locations órfãs pós-edit). Sem isso, queries
    de reuse_findings podiam retornar locations apontando pra arquivos já
    re-parseados, confundindo audit.
    """
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
    # ``reuse_finding_locations`` tem FK ON DELETE CASCADE no schema, mas
    # depende de FOREIGN_KEYS=ON estar ativo (default em open_db). Limpeza
    # explícita aqui é defesa em profundidade — se o pragma estiver off por
    # qualquer razão (fixture, migration in-flight), o purge mantém o invariante.
    conn.execute(
        "DELETE FROM reuse_finding_locations WHERE file_id = ?", (file_id,)
    )
    conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
