"""Full graph rebuild — walks the repo, parses every relevant file, and
populates SQLite tables defined in `engine/utils/sqlite_io.py`.

This is the heavy path: invoked by `forge init` and the "rebuild do graph"
escape hatch. For per-edit deltas use `engine.graph.incremental`.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from engine.graph.parser_kotlin import KotlinFileInfo, parse_kotlin_file
from engine.graph.parser_swift import SwiftFileInfo, parse_swift_file
from engine.graph.parser_typescript import TypeScriptFileInfo, parse_typescript_file
from engine.inventory.design_system import read_design_system_inventory
from engine.utils.paths import graph_db_path
from engine.utils.sqlite_io import open_db, set_meta, transaction

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
        _reset_domain_tables(conn)
        files_by_ext = discover_source_files(project_root)
        total_files = sum(len(paths) for paths in files_by_ext.values())

        files_scanned = 0
        symbols_extracted = 0
        edges_created = 0

        with transaction(conn):
            for ext in sorted(files_by_ext):
                for file_path in sorted(files_by_ext[ext]):
                    if progress_cb is not None:
                        progress_cb("parsing", files_scanned + 1, total_files)
                    stats = _ingest_file(conn, project_root, file_path, ext)
                    files_scanned += 1
                    symbols_extracted += stats["symbols"]
                    edges_created += stats["edges"]

            _populate_ds_components_from_inventory(conn, project_root)
            _populate_ds_usage_post_pass(conn)
            _populate_screens(conn)
            _populate_routes(conn)
            _populate_tests(conn)
            _resolve_import_targets(conn)
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


def _parse_gitignore(project_root: Path) -> list[tuple[str, bool, bool]]:
    """Parse `.gitignore` (best-effort) — supports nested files in subdirs.

    Returns a list of `(pattern, is_negation, dir_only)` where `pattern` is
    rooted at `project_root` (i.e., already prefixed with the relative dir of
    the `.gitignore` file when applicable). Tolerant to missing files.

    Supports: `*`, `**`, leading `/` (root-anchored), trailing `/` (dir-only),
    leading `!` (negation), comments (`#`), blank lines.

    Bracket character classes `[abc]` and brace expansion `{a,b}` are not
    supported — patterns containing them fall back to literal matching.
    """
    rules: list[tuple[str, bool, bool]] = []
    try:
        gitignores = list(project_root.rglob(".gitignore"))
    except (PermissionError, OSError):
        return rules

    for gi_path in gitignores:
        try:
            if any(part in _EXCLUDED_DIRS for part in gi_path.relative_to(project_root).parts):
                continue
        except ValueError:
            continue
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
            line = raw_line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            line = line.strip()
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
    """Return True if `path` is ignored. Last matching rule wins (gitignore semantics)."""
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


_GLOB_TRANSLATE_CACHE: dict[str, re.Pattern[str]] = {}


def _glob_translate(pattern: str) -> re.Pattern[str]:
    cached = _GLOB_TRANSLATE_CACHE.get(pattern)
    if cached is not None:
        return cached
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                if i + 2 < len(pattern) and pattern[i + 2] == "/":
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if ch == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(ch))
        i += 1
    regex = re.compile("^" + "".join(out) + "(?:/.*)?$")
    _GLOB_TRANSLATE_CACHE[pattern] = regex
    return regex


def _glob_match(rel_path: str, pattern: str) -> bool:
    if "[" in pattern or "{" in pattern:
        return fnmatch.fnmatch(rel_path, pattern)
    return _glob_translate(pattern).match(rel_path) is not None


def _reset_domain_tables(conn: sqlite3.Connection) -> None:
    """Wipe all domain tables (keep schema + meta intact)."""
    tables_to_clear = [
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
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in tables_to_clear:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("PRAGMA foreign_keys = ON")


def _ingest_file(
    conn: sqlite3.Connection,
    project_root: Path,
    file_path: Path,
    ext: str,
) -> dict:
    """Insert file row + parsed contents. Returns per-file stats."""
    language = _LANGUAGE_EXTENSIONS[ext]
    rel = _relpath(project_root, file_path)
    module = _infer_module(rel)

    try:
        raw = file_path.read_bytes()
    except OSError:
        return {"symbols": 0, "edges": 0}

    sha256 = hashlib.sha256(raw).hexdigest()
    line_count = raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1)
    last_modified = datetime.fromtimestamp(
        file_path.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    cursor = conn.execute(
        "INSERT INTO files(path, language, module, lines, last_modified, sha256) "
        "VALUES(?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET "
        "  language=excluded.language, module=excluded.module, "
        "  lines=excluded.lines, last_modified=excluded.last_modified, "
        "  sha256=excluded.sha256",
        (rel, language, module, line_count, last_modified, sha256),
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
            "INSERT INTO symbols(file_id, name, kind, signature, line_start, line_end, visibility) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (file_id, symbol.name, symbol.kind, None, symbol.line, symbol.line, "public"),
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
        (file_id, s.name, s.kind, None, s.line, s.line, "public") for s in info.symbols
    ]
    if symbol_rows:
        conn.executemany(
            "INSERT INTO symbols(file_id, name, kind, signature, line_start, line_end, visibility) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
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
        (file_id, s.name, s.kind, None, s.line, s.line, "public") for s in info.symbols
    ]
    component_rows = [
        (file_id, comp, "react_component", None, 0, 0, "public") for comp in info.components
    ]
    all_symbol_rows = symbol_rows + component_rows
    if all_symbol_rows:
        conn.executemany(
            "INSERT INTO symbols(file_id, name, kind, signature, line_start, line_end, visibility) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
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
    except Exception:
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
