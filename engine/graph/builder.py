"""Full graph rebuild — walks the repo, parses every relevant file, and
populates SQLite tables defined in `engine/utils/sqlite_io.py`.

This is the heavy path: invoked by `forge init` and the "rebuild do graph"
escape hatch. For per-edit deltas use `engine.graph.incremental`.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from pathspec import PathSpec
from pathspec.patterns.gitignore.spec import GitIgnoreSpecPattern

from engine.graph.gradle_deps import (
    parse_module_dependencies,
    persist_module_dependencies,
)
from engine.graph.gradle_modules import (
    infer_module_and_source_set,
    load_gradle_modules,
)
from engine.graph.parser_kotlin import KotlinFileInfo, parse_kotlin_file
from engine.graph.parser_swift import SwiftFileInfo, parse_swift_file
from engine.graph.parser_typescript import TypeScriptFileInfo, parse_typescript_file
from engine.inventory.design_system import read_design_system_inventory
from engine.utils.paths import graph_db_path
from engine.utils.sqlite_io import open_db, set_meta, transaction
from engine.utils.yaml_io import YamlIOError

_EXCLUDED_DIRS = frozenset(
    {
        "node_modules",
        "build",
        ".git",
        ".gradle",
        ".idea",
        ".vscode",
        "DerivedData",
        "Pods",
        "target",
        "dist",
        ".next",
        ".cache",
        ".turbo",
        "vendor",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        ".claude",
    }
)

_LANGUAGE_EXTENSIONS = {
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
}

ProgressCb = Callable[[str, int, int], None]


def build_full(
    project_root: Path,
    db_path: Optional[Path] = None,
    *,
    progress_cb: Optional[ProgressCb] = None,
) -> dict:
    """Full rebuild. Drops domain tables, walks the project, repopulates.

    Returns a stats dict suitable for logging / display.
    """
    start = time.perf_counter()
    target_db = db_path or graph_db_path(project_root)
    conn = open_db(target_db, create=True)
    try:
        _ensure_imports_to_file_id_column(conn)
        _ensure_reuse_intelligence_columns(conn)
        _reset_domain_tables(conn)
        files_by_ext = discover_source_files(project_root)
        total_files = sum(len(paths) for paths in files_by_ext.values())

        files_scanned = 0
        symbols_extracted = 0
        edges_created = 0

        with transaction(conn):
            gradle_modules = load_gradle_modules(project_root)
            module_dep_rows = parse_module_dependencies(project_root, gradle_modules)
            persist_module_dependencies(conn, module_dep_rows)

            for ext in sorted(files_by_ext):
                for file_path in sorted(files_by_ext[ext]):
                    if progress_cb is not None:
                        progress_cb("parsing", files_scanned + 1, total_files)
                    stats = _ingest_file(
                        conn, project_root, file_path, ext, gradle_modules
                    )
                    files_scanned += 1
                    symbols_extracted += stats["symbols"]
                    edges_created += stats["edges"]

            _populate_ds_components_from_inventory(conn, project_root)
            _populate_ds_usage_post_pass(conn)
            _populate_screens(conn)
            _populate_routes(conn)
            _populate_tests(conn)
            _resolve_import_targets(conn)

            from engine.graph.duplicates import detect_all_reuse_findings
            detect_all_reuse_findings(conn, gradle_modules, module_dep_rows)

            set_meta(conn, "last_full_rebuild_at", datetime.now(timezone.utc).isoformat())

        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "files_scanned": files_scanned,
            "symbols_extracted": symbols_extracted,
            "edges_created": edges_created,
            "duration_ms": duration_ms,
        }
    finally:
        conn.close()


def discover_source_files(project_root: Path) -> dict[str, list[Path]]:
    """Walk project_root respecting common excludes + .gitignore. Returns ext → [paths]."""
    root = project_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"project_root does not exist: {root}")

    gitignore_rules = _parse_gitignore(root)

    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in _iter_files(root, gitignore_rules):
        ext = path.suffix.lower()
        if ext in _LANGUAGE_EXTENSIONS:
            grouped[ext].append(path)

    return {ext: sorted(paths) for ext, paths in grouped.items()}


def _iter_files(root: Path, gitignore_rules: Optional[list[tuple[str, bool, bool]]] = None):
    rules = gitignore_rules or []
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            name = entry.name
            is_dir = entry.is_dir()
            if name.startswith(".") and name not in {".github"}:
                if is_dir and name in _EXCLUDED_DIRS:
                    continue
                if is_dir:
                    continue
            if is_dir:
                if name in _EXCLUDED_DIRS:
                    continue
                if rules and _matches_gitignore(entry, root, rules, is_dir=True):
                    continue
                stack.append(entry)
            elif entry.is_file():
                if rules and _matches_gitignore(entry, root, rules, is_dir=False):
                    continue
                yield entry


def _find_gitignore_files(project_root: Path) -> list[Path]:
    """Return absolute paths of every `.gitignore` reachable from `project_root`.

    Uses `os.scandir` recursively and skips `_EXCLUDED_DIRS` + symlinks ANTES
    da descida — `Path.rglob` desce em `node_modules`/`build`/`.gradle` antes
    de qualquer filtro, o que trava em monorepos mobile grandes. Tolerante a
    `PermissionError`/`OSError` por subárvore. Ordem do retorno é irrelevante.
    """
    found: list[Path] = []
    # Tracking visited real-paths previne loop infinito em symlink cycles
    # (raros mas devastadores). Mesmo com `follow_symlinks=False`, cobrimos
    # hard links e bind mounts esquisitos com baixo custo (set lookup).
    visited: set[str] = set()
    stack: list[Path] = [project_root]
    while stack:
        current = stack.pop()
        try:
            real = os.path.realpath(current)
        except OSError:
            continue
        if real in visited:
            continue
        visited.add(real)
        try:
            it = os.scandir(current)
        except (PermissionError, OSError, FileNotFoundError):
            continue
        with it:
            for entry in it:
                name = entry.name
                try:
                    is_symlink = entry.is_symlink()
                except OSError:
                    is_symlink = False
                if is_symlink:
                    # Nunca segue symlinks — evita loops e prevents
                    # escapar do project_root via link aleatório.
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir:
                    if name in _EXCLUDED_DIRS:
                        continue
                    stack.append(Path(entry.path))
                elif name == ".gitignore":
                    found.append(Path(entry.path))
    return found


# M-07 + M-08: replaced custom parser with `pathspec` (canonical gitignore
# semantics). The old parser missed bracket classes, escapes, trailing
# spaces, and `a/**/b` middle-double-star; the custom regex over-matched
# directories ending in the pattern's suffix.
def _parse_gitignore(project_root: Path) -> list[tuple[str, bool, bool]]:
    """Parse `.gitignore` (best-effort) — supports nested files in subdirs.

    Returns a list of `(pattern, is_negation, dir_only)`. Pattern rooted at
    `project_root`. Tolerant to missing files.

    Backed by `pathspec` (M-07): supports bracket classes `[abc]`,
    escaped chars `\\#`, trailing spaces, and `a/**/b` middle-double-star.
    """
    rules: list[tuple[str, bool, bool]] = []
    gitignores = _find_gitignore_files(project_root)

    for gi_path in gitignores:
        try:
            lines = gi_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        try:
            rel_dir = str(gi_path.parent.relative_to(project_root)).replace("\\", "/")
        except ValueError:
            rel_dir = ""
        if rel_dir == ".":
            rel_dir = ""

        for raw_line in lines:
            line = raw_line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            negation = line.startswith("!")
            if negation:
                line = line[1:]
            dir_only = line.endswith("/")
            if dir_only:
                line = line[:-1]
            anchored = line.startswith("/")
            if anchored:
                line = line[1:]
            if not line:
                continue
            if rel_dir:
                pattern = f"{rel_dir}/{line}" if (anchored or "/" in line) else f"{rel_dir}/**/{line}"
            else:
                pattern = line if (anchored or "/" in line) else f"**/{line}"
            rules.append((pattern, negation, dir_only))
    return rules


def _matches_gitignore(
    path: Path,
    project_root: Path,
    rules: list[tuple[str, bool, bool]],
    *,
    is_dir: bool,
) -> bool:
    """Return True if `path` is ignored. Last matching rule wins."""
    try:
        rel = path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        return False
    if not rel:
        return False

    ignored = False
    for pattern, negation, dir_only in rules:
        if dir_only and not is_dir:
            continue
        if _glob_match(rel, pattern):
            ignored = not negation
    return ignored


_PATHSPEC_CACHE: dict[str, PathSpec] = {}


def _glob_match(rel_path: str, pattern: str) -> bool:
    """pathspec-backed match. Encodes canonical gitignore semantics."""
    spec = _PATHSPEC_CACHE.get(pattern)
    if spec is None:
        spec = PathSpec.from_lines(GitIgnoreSpecPattern, [pattern])
        _PATHSPEC_CACHE[pattern] = spec
    return spec.match_file(rel_path)


# H-01 (security): defensive allowlist. Any new domain table added to
# `tables_to_clear` must also land here, or _reset_domain_tables refuses
# to wipe it. Prevents SQL-injection-like surface if a future refactor
# ever sources table names from external config.
_ALLOWED_TABLES: frozenset[str] = frozenset({
    "reuse_finding_locations",
    "reuse_findings",
    "module_deps",
    "ds_usage",
    "ds_components",
    "i18n_usage",
    "i18n_keys",
    "imports",
    "tests",
    "screens",
    "routes",
    "di_graph",
    "symbols",
    "files",
})


# Canonical default order (FK-children first) used by _reset_domain_tables.
# Extracted as module-level constant so tests can verify the allowlist guard
# fires by passing in a tampered list — without re-inlining the validation
# logic into the test itself (WR-01 / final review 2026-06-15).
_DEFAULT_TABLES_TO_CLEAR: list[str] = [
    "reuse_finding_locations",
    "reuse_findings",
    "module_deps",
    "ds_usage",
    "ds_components",
    "i18n_usage",
    "i18n_keys",
    "imports",
    "tests",
    "screens",
    "routes",
    "di_graph",
    "symbols",
    "files",
]


def _reset_domain_tables(
    conn: sqlite3.Connection,
    *,
    tables: list[str] | None = None,
) -> None:
    """Wipe all domain tables (keep schema + meta intact).

    Reuse-intelligence tables (`module_deps`, `reuse_findings`,
    `reuse_finding_locations`) are also cleared — they're re-derived during the
    post-passes from settings.gradle, build.gradle and symbol contents.

    The ``tables`` kw-only parameter exists ONLY for regression-test injection
    (WR-01): tests pass a tampered list to assert the allowlist guard fires
    on unknown table names. Production callers MUST NOT pass it — leave it
    as ``None`` to use ``_DEFAULT_TABLES_TO_CLEAR``.
    """
    # HG-01 (review): refuse to run inside an outer transaction. Two reasons:
    #   1. ``PRAGMA foreign_keys`` is silently ignored mid-transaction
    #      (SQLite contract), so the OFF/ON toggle below becomes a no-op
    #      and FK enforcement keeps running through the wipes — undermining
    #      the whole purpose of this function.
    #   2. The inner ``with conn:`` block below opens an implicit
    #      transaction. If we are already inside an outer transaction, the
    #      rollback path of that ``with`` block reverts the OUTER tx, not
    #      a nested one — corrupting state the caller relied on.
    # Loud assertion > silent corruption.
    assert not conn.in_transaction, (
        "_reset_domain_tables must run outside an open transaction "
        "(PRAGMA foreign_keys is a no-op inside transactions; "
        "the inner `with conn:` rollback would target the outer "
        "transaction, corrupting state)."
    )

    tables_to_clear = tables if tables is not None else _DEFAULT_TABLES_TO_CLEAR
    # PRAGMA foreign_keys must run outside a transaction (SQLite ignores it
    # mid-transaction). The DELETEs themselves go inside an implicit
    # transaction (`with conn:`) so a mid-stream failure rolls back the
    # partial wipe. The `try/finally` guarantees the pragma is restored to
    # ON even when a DELETE raises — otherwise the connection would leak
    # ``foreign_keys = OFF`` into subsequent transactions, silently
    # disabling FK enforcement for the rest of its life.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            for table in tables_to_clear:
                if table not in _ALLOWED_TABLES:
                    raise ValueError(
                        f"Blocked unauthorized table wipe: {table}"
                    )
                conn.execute(f"DELETE FROM {table}")  # noqa: S608 — allowlist-validated
    finally:
        # H-04: PRAGMA restore is best-effort. If the connection is closing
        # (or the DELETE above already raised), we still try to flip FK back
        # on; failure here must NOT mask the original exception.
        #
        # A-007 (master review PR #15): explicit — `ValueError` do guard de
        # allowlist (linhas 368-371) também passa por este `finally`. PRAGMA
        # é restaurado mesmo quando o erro foi de validação (allowlist miss),
        # não apenas de I/O do DELETE. Sem este finally, validation-error
        # deixaria FKs desabilitadas pra resto da vida da conexão.
        try:
            conn.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error:
            pass


def _ingest_file(
    conn: sqlite3.Connection,
    project_root: Path,
    file_path: Path,
    ext: str,
    gradle_modules: Optional[dict[str, str]] = None,
) -> dict:
    """Insert file row + parsed contents. Returns per-file stats."""
    language = _LANGUAGE_EXTENSIONS[ext]
    rel = _relpath(project_root, file_path)
    module, source_set = infer_module_and_source_set(rel, gradle_modules or {})

    try:
        raw = file_path.read_bytes()
    except OSError:
        return {"symbols": 0, "edges": 0}

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
    file_id = conn.execute("SELECT id FROM files WHERE path = ?", (rel,)).fetchone()["id"]

    if language == "kotlin":
        info = parse_kotlin_file(file_path)
        return _persist_kotlin(conn, file_id, info)
    if language == "swift":
        info_sw = parse_swift_file(file_path)
        return _persist_swift(conn, file_id, info_sw)
    if language in {"typescript", "javascript"}:
        info_ts = parse_typescript_file(file_path)
        return _persist_typescript(conn, file_id, info_ts)
    return {"symbols": 0, "edges": 0}


_DI_ANNOTATION_TO_KIND = {
    "Single": "single",
    "Factory": "factory",
    "KoinViewModel": "viewmodel",
    "Module": "module",
    "ComponentScan": "module",
    "Scope": "scoped",
    "Scoped": "scoped",
}


def _persist_kotlin(conn: sqlite3.Connection, file_id: int, info: KotlinFileInfo) -> dict:
    # Kotlin precisa de lastrowid por símbolo para preencher di_graph; mantemos
    # loop em symbols mas usamos executemany em imports / firebase_refs / di.
    edges = 0
    name_to_symbol_id: dict[str, int] = {}
    for symbol in info.symbols:
        cur = conn.execute(
            "INSERT INTO symbols("
            "  file_id, name, kind, signature, line_start, line_end, visibility, "
            "  receiver_type, body_hash, body_tokens, modifiers"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_id,
                symbol.name,
                symbol.kind,
                symbol.signature,
                symbol.line,
                symbol.line,
                symbol.visibility,
                symbol.receiver_type,
                symbol.body_hash,
                symbol.body_tokens,
                " ".join(symbol.modifiers) if symbol.modifiers else None,
            ),
        )
        if cur.lastrowid is not None:
            name_to_symbol_id[symbol.name] = cur.lastrowid

    import_rows = [(file_id, imp) for imp in info.imports]
    if import_rows:
        conn.executemany(
            "INSERT INTO imports(from_file_id, to_symbol, kind) VALUES(?, ?, 'import')",
            import_rows,
        )
        edges += len(import_rows)

    firebase_rows = [(file_id, ref) for ref in info.firebase_refs]
    if firebase_rows:
        conn.executemany(
            "INSERT INTO imports(from_file_id, to_symbol, kind) VALUES(?, ?, 'firebase_ref')",
            firebase_rows,
        )
        edges += len(firebase_rows)

    di_rows: list[tuple[int, int, str, str]] = []
    for di in info.di_annotations:
        sym_id = name_to_symbol_id.get(di["class_name"])
        if sym_id is None:
            continue
        scope = _DI_ANNOTATION_TO_KIND.get(di["annotation"], "unknown")
        di_rows.append((sym_id, sym_id, scope, di["annotation"]))
    if di_rows:
        conn.executemany(
            "INSERT INTO di_graph(provider_symbol_id, consumer_symbol_id, scope, kind) "
            "VALUES(?, ?, ?, ?)",
            di_rows,
        )

    _record_i18n_usage(conn, file_id, info.i18n_keys_used)
    return {"symbols": len(info.symbols), "edges": edges}


def _persist_swift(conn: sqlite3.Connection, file_id: int, info: SwiftFileInfo) -> dict:
    # Swift não consome lastrowid — podemos executemany em symbols e imports.
    edges = 0
    symbol_rows = [
        (
            file_id,
            s.name,
            s.kind,
            s.signature,
            s.line,
            s.line,
            s.visibility,
            s.receiver_type,
            s.body_hash,
            s.body_tokens,
            " ".join(s.modifiers) if s.modifiers else None,
        )
        for s in info.symbols
    ]
    if symbol_rows:
        conn.executemany(
            "INSERT INTO symbols("
            "  file_id, name, kind, signature, line_start, line_end, visibility, "
            "  receiver_type, body_hash, body_tokens, modifiers"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            symbol_rows,
        )

    import_rows = [(file_id, imp) for imp in info.imports]
    if import_rows:
        conn.executemany(
            "INSERT INTO imports(from_file_id, to_symbol, kind) VALUES(?, ?, 'import')",
            import_rows,
        )
        edges += len(import_rows)

    _record_i18n_usage(conn, file_id, info.i18n_keys_used)
    return {"symbols": len(info.symbols), "edges": edges}


def _persist_typescript(conn: sqlite3.Connection, file_id: int, info: TypeScriptFileInfo) -> dict:
    # TS também sem lastrowid — batch tudo via executemany.
    edges = 0
    symbol_rows = [
        (
            file_id,
            s.name,
            s.kind,
            s.signature,
            s.line,
            s.line,
            s.visibility,
            None,
            s.body_hash,
            s.body_tokens,
            " ".join(s.modifiers) if s.modifiers else None,
        )
        for s in info.symbols
    ]
    component_rows = [
        (file_id, comp, "react_component", None, 0, 0, "public", None, None, None, None)
        for comp in info.components
    ]
    all_symbol_rows = symbol_rows + component_rows
    if all_symbol_rows:
        conn.executemany(
            "INSERT INTO symbols("
            "  file_id, name, kind, signature, line_start, line_end, visibility, "
            "  receiver_type, body_hash, body_tokens, modifiers"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            all_symbol_rows,
        )

    import_rows = [(file_id, imp) for imp in info.imports]
    if import_rows:
        conn.executemany(
            "INSERT INTO imports(from_file_id, to_symbol, kind) VALUES(?, ?, 'import')",
            import_rows,
        )
        edges += len(import_rows)

    _record_i18n_usage(conn, file_id, info.i18n_keys_used)
    symbol_total = len(info.symbols) + len(info.components)
    return {"symbols": symbol_total, "edges": edges}


def _record_i18n_usage(conn: sqlite3.Connection, file_id: int, keys: list[str]) -> None:
    """Upsert i18n_keys (locale='_usage') + insert i18n_usage rows.

    The schema requires i18n_keys for every i18n_usage row (FK). We synthesize a
    sentinel locale `_usage` for keys observed only at call sites, so usage is
    captured even when the inventory hasn't fully indexed translation files.
    """
    for key in keys:
        if not key:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO i18n_keys(key, locale, value, source_file_id) "
            "VALUES(?, '_usage', NULL, ?)",
            (key, file_id),
        )
        row = conn.execute(
            "SELECT id FROM i18n_keys WHERE key = ? AND locale = '_usage'", (key,)
        ).fetchone()
        if row is None:
            continue
        conn.execute(
            "INSERT INTO i18n_usage(key_id, file_id, line) VALUES(?, ?, ?)",
            (row["id"], file_id, -1),
        )


def _populate_ds_components_from_inventory(conn: sqlite3.Connection, project_root: Path) -> None:
    """Seed ds_components from `.claude/inventory/design-system.yaml` if present."""
    try:
        inv = read_design_system_inventory(project_root)
    except (OSError, UnicodeDecodeError, YamlIOError, KeyError, TypeError, AttributeError):
        # B-004 (master review PR #15): cada tipo é esperado, não shotgun.
        # - OSError: filesystem read em inventory_dir
        # - UnicodeDecodeError: design-system.yaml com encoding inválido
        # - YamlIOError: parser do read_yaml em YAML malformado
        # - KeyError: `c["name"]` em entry de components sem o campo
        # - TypeError: `dict(c.get("paths") or {})` quando `paths` não é mapping
        # - AttributeError: `tokens_raw.get(...)` quando o nó é list em vez de dict
        # Seed é best-effort; inventory inválido vira ds_components vazio (cascade
        # segue com graph parcial em vez de explodir o builder inteiro).
        inv = None
    if inv is None:
        return
    for comp in inv.components:
        paths = comp.paths or {}
        conn.execute(
            "INSERT INTO ds_components(name, level, status, path_android, path_ios, path_web) "
            "VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "  level=excluded.level, status=excluded.status, "
            "  path_android=excluded.path_android, path_ios=excluded.path_ios, "
            "  path_web=excluded.path_web",
            (
                comp.name,
                comp.level,
                comp.status,
                paths.get("android"),
                paths.get("ios"),
                paths.get("web"),
            ),
        )


def _populate_ds_usage_post_pass(conn: sqlite3.Connection) -> None:
    """Cross-ref ds_components with imports — each import ending in `.{Name}`
    or with `to_symbol` equal to the component name counts as one occurrence.
    """
    components = conn.execute("SELECT id, name FROM ds_components").fetchall()
    if not components:
        return
    for comp in components:
        comp_id = comp["id"]
        comp_name = comp["name"]
        rows = conn.execute(
            "SELECT from_file_id, COUNT(*) AS n FROM imports "
            "WHERE to_symbol = ? OR to_symbol LIKE ? "
            "GROUP BY from_file_id",
            (comp_name, f"%.{comp_name}"),
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO ds_usage(component_id, screen_id, file_id, occurrences) "
                "VALUES(?, NULL, ?, ?)",
                (comp_id, row["from_file_id"], row["n"]),
            )


def _populate_screens(conn: sqlite3.Connection) -> None:
    """Detect screen files by naming convention and link to a synthesized feature row."""
    candidates = conn.execute(
        "SELECT id, path FROM files "
        "WHERE path LIKE '%Screen.kt' OR path LIKE '%ScreenView.swift' "
        "   OR path LIKE '%Page.tsx' OR path LIKE '%Page.jsx'"
    ).fetchall()
    for row in candidates:
        file_id = row["id"]
        rel = row["path"]
        feature_slug = _infer_feature_slug(rel)
        if feature_slug is None:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO features(slug, status, created_at, last_activity, modules) "
            "VALUES(?, 'detected', NULL, NULL, NULL)",
            (feature_slug,),
        )
        screen_name = _screen_name_from_path(rel)
        conn.execute(
            "INSERT INTO screens(feature_slug, name, file_id, route_id) VALUES(?, ?, ?, NULL)",
            (feature_slug, screen_name, file_id),
        )


def _populate_routes(conn: sqlite3.Connection) -> None:
    """Detect route declarations — Kotlin sealed classes/objects extending AppRoute
    or named `*Route`, Swift enum cases similar pattern, TS exports ending in `Route`.
    """
    rows = conn.execute(
        "SELECT s.id, s.name, s.kind, s.file_id FROM symbols s "
        "WHERE s.name LIKE '%Route' OR s.name = 'AppRoute' OR s.kind = 'sealed_class'"
    ).fetchall()
    seen: set[str] = set()
    for row in rows:
        key = row["name"]
        if key in seen:
            continue
        seen.add(key)
        conn.execute(
            "INSERT OR IGNORE INTO routes(key, params_json, type, defined_in_file) "
            "VALUES(?, NULL, ?, ?)",
            (key, row["kind"], row["file_id"]),
        )


def _populate_tests(conn: sqlite3.Connection) -> None:
    """Detect test files by naming and try to infer the target production file."""
    rows = conn.execute(
        "SELECT id, path, language FROM files "
        "WHERE path LIKE '%Test.kt' OR path LIKE '%Tests.swift' "
        "   OR path LIKE '%.test.ts' OR path LIKE '%.test.tsx' "
        "   OR path LIKE '%.spec.ts' OR path LIKE '%.spec.tsx'"
    ).fetchall()
    for row in rows:
        file_id = row["id"]
        rel = row["path"]
        framework = _infer_test_framework(rel, row["language"])
        target_id = _infer_test_target_file_id(conn, rel)
        conn.execute(
            "INSERT INTO tests(file_id, target_file_id, kind, status) VALUES(?, ?, ?, 'unknown')",
            (file_id, target_id, framework),
        )


def _resolve_import_targets(conn: sqlite3.Connection) -> None:
    """Best-effort: set `imports.to_file_id` when `to_symbol` matches a known symbol.

    The schema's `to_symbol` is a fully-qualified path like `com.foo.Bar`; we
    match against symbols.name by suffix (`%.Name` or exact). When multiple
    files own the same symbol name, escolhemos por `ORDER BY f.path, s.name`.

    F9: `MIN(s.file_id)` era instável across incremental updates — file_ids
    podem mudar quando arquivos são removidos/readicionados, então o mesmo
    import resolvia para alvos diferentes entre runs. `f.path` é estável
    por definição (vem do filesystem).
    """
    conn.execute(
        """
        UPDATE imports
        SET to_file_id = (
            SELECT s.file_id
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.name = imports.to_symbol
               OR imports.to_symbol LIKE '%.' || s.name
            ORDER BY f.path, s.name
            LIMIT 1
        )
        WHERE to_file_id IS NULL
        """
    )


def _ensure_imports_to_file_id_column(conn: sqlite3.Connection) -> None:
    """Migration: add `imports.to_file_id` column when missing (legacy DBs)."""
    cols = conn.execute("PRAGMA table_info(imports)").fetchall()
    names = {c["name"] for c in cols}
    if "to_file_id" not in names:
        conn.execute("ALTER TABLE imports ADD COLUMN to_file_id INTEGER REFERENCES files(id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_imports_to_file ON imports(to_file_id)")


def _ensure_reuse_intelligence_columns(conn: sqlite3.Connection) -> None:
    """Migration: add reuse-intelligence columns and tables for legacy DBs (schema v2).

    Adds:
      - files.source_set
      - symbols.{receiver_type, body_hash, body_tokens, modifiers}
      - module_deps, reuse_findings, reuse_finding_locations tables (+ indexes)
    """
    files_cols = {c["name"] for c in conn.execute("PRAGMA table_info(files)").fetchall()}
    if "source_set" not in files_cols:
        conn.execute("ALTER TABLE files ADD COLUMN source_set TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_source_set ON files(source_set)")

    symbols_cols = {c["name"] for c in conn.execute("PRAGMA table_info(symbols)").fetchall()}
    if "receiver_type" not in symbols_cols:
        conn.execute("ALTER TABLE symbols ADD COLUMN receiver_type TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_symbols_receiver_type ON symbols(receiver_type)")
    if "body_hash" not in symbols_cols:
        conn.execute("ALTER TABLE symbols ADD COLUMN body_hash TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_symbols_body_hash ON symbols(body_hash)")
    if "body_tokens" not in symbols_cols:
        conn.execute("ALTER TABLE symbols ADD COLUMN body_tokens TEXT")
    if "modifiers" not in symbols_cols:
        conn.execute("ALTER TABLE symbols ADD COLUMN modifiers TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS module_deps (
          from_module TEXT NOT NULL,
          to_module   TEXT NOT NULL,
          scope       TEXT,
          PRIMARY KEY (from_module, to_module, scope)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_module_deps_from ON module_deps(from_module)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_module_deps_to   ON module_deps(to_module)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reuse_findings (
          id                  INTEGER PRIMARY KEY AUTOINCREMENT,
          category            TEXT NOT NULL,
          group_id            TEXT NOT NULL UNIQUE,
          symbol_name         TEXT NOT NULL,
          receiver_type       TEXT,
          canonical_signature TEXT,
          body_hash           TEXT,
          primary_language    TEXT NOT NULL,
          modifiers           TEXT,
          suggested_target    TEXT,
          confidence          REAL NOT NULL,
          similarity_score    REAL,
          detected_at         TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reuse_findings_category ON reuse_findings(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reuse_findings_group    ON reuse_findings(group_id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reuse_finding_locations (
          finding_id  INTEGER NOT NULL REFERENCES reuse_findings(id) ON DELETE CASCADE,
          file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          module      TEXT NOT NULL,
          source_set  TEXT,
          line_start  INTEGER NOT NULL,
          language    TEXT NOT NULL,
          body_hash   TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reuse_finding_locations_finding "
        "ON reuse_finding_locations(finding_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reuse_finding_locations_file "
        "ON reuse_finding_locations(file_id)"
    )


_FEATURE_DIR_RE = re.compile(r"(?:^|/)(?:feature|features)/([a-zA-Z0-9_\-]+)/")


def _infer_feature_slug(rel_path: str) -> Optional[str]:
    norm = rel_path.replace("\\", "/")
    m = _FEATURE_DIR_RE.search("/" + norm)
    if m:
        return m.group(1)
    return None


def _screen_name_from_path(rel_path: str) -> str:
    stem = Path(rel_path).stem
    for suffix in ("ScreenView", "Screen", "Page"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)] or stem
    return stem


def _infer_test_framework(rel_path: str, language: Optional[str]) -> str:
    norm = rel_path.lower()
    if norm.endswith((".test.tsx", ".spec.tsx", ".test.jsx", ".spec.jsx")):
        return "ui"
    if "uitest" in norm or "uitests" in norm:
        return "ui"
    if language in {"kotlin", "swift"}:
        return "unit"
    return "unit"


def _infer_test_target_file_id(conn: sqlite3.Connection, rel_path: str) -> Optional[int]:
    """Naming heuristic: `FooTest.kt` → look for `Foo.kt`, `FooTests.swift` → `Foo.swift`,
    `Foo.test.ts` → `Foo.ts` (also `.tsx`).
    """
    p = Path(rel_path)
    stem = p.stem
    suffix = p.suffix
    candidates: list[str] = []

    if stem.endswith(".test") or stem.endswith(".spec"):
        base = stem.rsplit(".", 1)[0]
        for ext in (suffix, ".tsx" if suffix == ".ts" else ".ts"):
            candidates.append(f"{base}{ext}")
    elif stem.endswith("Tests"):
        base = stem[: -len("Tests")]
        candidates.append(f"{base}{suffix}")
    elif stem.endswith("Test"):
        base = stem[: -len("Test")]
        candidates.append(f"{base}{suffix}")

    if not candidates:
        return None

    for cand in candidates:
        row = conn.execute(
            "SELECT id FROM files WHERE path LIKE ? ORDER BY LENGTH(path) ASC LIMIT 1",
            (f"%{cand}",),
        ).fetchone()
        if row is not None:
            return row["id"]
    return None


def _relpath(project_root: Path, file_path: Path) -> str:
    try:
        return str(file_path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(file_path)


def _infer_module(rel_path: str) -> str:
    """Pick the first path segment as the Gradle/module name (heuristic)."""
    parts = rel_path.replace("\\", "/").split("/")
    return parts[0] if parts and parts[0] else "<root>"
