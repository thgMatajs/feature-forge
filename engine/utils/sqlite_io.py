"""SQLite I/O wrapper with WAL mode + transactional helpers.

The graph DB lives at `.claude/graph.db` and is accessed concurrently by:
- `forge graph` (read queries)
- `forge ingest` triggered by hooks (incremental writes)
- `forge reconfigure` (full rebuild)

WAL mode lets readers and writers coexist without blocking. The full schema
is documented in `docs/schemas/graph.md`; this module ships the canonical
DDL so a fresh `.claude/graph.db` can be bootstrapped without parsing markdown.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Sequence

SCHEMA_VERSION = "2"

# Full DDL — kept in sync with docs/schemas/graph.md.
# Adding a table here without updating the schema doc is a documentation bug.
_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS files (
  id              INTEGER PRIMARY KEY,
  path            TEXT NOT NULL UNIQUE,
  language        TEXT,
  module          TEXT,
  source_set      TEXT,
  lines           INTEGER,
  last_modified   TEXT,
  sha256          TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_module     ON files(module);
CREATE INDEX IF NOT EXISTS idx_files_language   ON files(language);
CREATE INDEX IF NOT EXISTS idx_files_source_set ON files(source_set);

CREATE TABLE IF NOT EXISTS symbols (
  id              INTEGER PRIMARY KEY,
  file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  kind            TEXT NOT NULL,
  signature       TEXT,
  line_start      INTEGER,
  line_end        INTEGER,
  visibility      TEXT,
  receiver_type   TEXT,
  body_hash       TEXT,
  body_tokens     TEXT,
  modifiers       TEXT
);
CREATE INDEX IF NOT EXISTS idx_symbols_name          ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_file          ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_kind          ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_symbols_receiver_type ON symbols(receiver_type);
CREATE INDEX IF NOT EXISTS idx_symbols_body_hash     ON symbols(body_hash);

CREATE TABLE IF NOT EXISTS imports (
  from_file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  to_symbol       TEXT NOT NULL,
  kind            TEXT
);
CREATE INDEX IF NOT EXISTS idx_imports_from ON imports(from_file_id);
CREATE INDEX IF NOT EXISTS idx_imports_to   ON imports(to_symbol);

CREATE TABLE IF NOT EXISTS features (
  slug            TEXT PRIMARY KEY,
  status          TEXT NOT NULL,
  created_at      TEXT,
  last_activity   TEXT,
  modules         TEXT
);
CREATE INDEX IF NOT EXISTS idx_features_status ON features(status);

CREATE TABLE IF NOT EXISTS routes (
  id              INTEGER PRIMARY KEY,
  key             TEXT NOT NULL UNIQUE,
  params_json     TEXT,
  type            TEXT,
  defined_in_file INTEGER REFERENCES files(id)
);

CREATE TABLE IF NOT EXISTS screens (
  id              INTEGER PRIMARY KEY,
  feature_slug    TEXT NOT NULL REFERENCES features(slug) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  file_id         INTEGER REFERENCES files(id),
  route_id        INTEGER REFERENCES routes(id)
);
CREATE INDEX IF NOT EXISTS idx_screens_feature ON screens(feature_slug);

CREATE TABLE IF NOT EXISTS ds_components (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  level           TEXT,
  status          TEXT,
  path_android    TEXT,
  path_ios        TEXT,
  path_web        TEXT
);
CREATE INDEX IF NOT EXISTS idx_ds_components_level  ON ds_components(level);
CREATE INDEX IF NOT EXISTS idx_ds_components_status ON ds_components(status);

CREATE TABLE IF NOT EXISTS ds_usage (
  component_id    INTEGER NOT NULL REFERENCES ds_components(id) ON DELETE CASCADE,
  screen_id       INTEGER REFERENCES screens(id),
  file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  occurrences     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_ds_usage_component ON ds_usage(component_id);
CREATE INDEX IF NOT EXISTS idx_ds_usage_screen    ON ds_usage(screen_id);

CREATE TABLE IF NOT EXISTS i18n_keys (
  id              INTEGER PRIMARY KEY,
  key             TEXT NOT NULL,
  locale          TEXT NOT NULL,
  value           TEXT,
  source_file_id  INTEGER REFERENCES files(id),
  UNIQUE(key, locale)
);
CREATE INDEX IF NOT EXISTS idx_i18n_keys_key ON i18n_keys(key);

CREATE TABLE IF NOT EXISTS i18n_usage (
  id              INTEGER PRIMARY KEY,
  key_id          INTEGER NOT NULL REFERENCES i18n_keys(id) ON DELETE CASCADE,
  file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  line            INTEGER
);
CREATE INDEX IF NOT EXISTS idx_i18n_usage_key  ON i18n_usage(key_id);
CREATE INDEX IF NOT EXISTS idx_i18n_usage_file ON i18n_usage(file_id);

CREATE TABLE IF NOT EXISTS di_graph (
  provider_symbol_id  INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
  consumer_symbol_id  INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
  scope               TEXT,
  kind                TEXT
);
CREATE INDEX IF NOT EXISTS idx_di_provider ON di_graph(provider_symbol_id);
CREATE INDEX IF NOT EXISTS idx_di_consumer ON di_graph(consumer_symbol_id);

CREATE TABLE IF NOT EXISTS tests (
  id              INTEGER PRIMARY KEY,
  file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  target_file_id  INTEGER REFERENCES files(id),
  kind            TEXT,
  status          TEXT
);
CREATE INDEX IF NOT EXISTS idx_tests_target ON tests(target_file_id);
CREATE INDEX IF NOT EXISTS idx_tests_kind   ON tests(kind);

CREATE TABLE IF NOT EXISTS feature_commits (
  feature_slug         TEXT NOT NULL REFERENCES features(slug),
  commit_sha           TEXT NOT NULL,
  files_touched_count  INTEGER,
  timestamp            TEXT,
  PRIMARY KEY (feature_slug, commit_sha)
);

CREATE TABLE IF NOT EXISTS task_commits (
  task_id              TEXT NOT NULL,
  commit_sha           TEXT NOT NULL,
  files_touched_count  INTEGER,
  timestamp            TEXT,
  PRIMARY KEY (task_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS module_deps (
  from_module TEXT NOT NULL,
  to_module   TEXT NOT NULL,
  scope       TEXT,
  PRIMARY KEY (from_module, to_module, scope)
);
CREATE INDEX IF NOT EXISTS idx_module_deps_from ON module_deps(from_module);
CREATE INDEX IF NOT EXISTS idx_module_deps_to   ON module_deps(to_module);

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
);
CREATE INDEX IF NOT EXISTS idx_reuse_findings_category ON reuse_findings(category);
CREATE INDEX IF NOT EXISTS idx_reuse_findings_group    ON reuse_findings(group_id);

CREATE TABLE IF NOT EXISTS reuse_finding_locations (
  finding_id  INTEGER NOT NULL REFERENCES reuse_findings(id) ON DELETE CASCADE,
  file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  module      TEXT NOT NULL,
  source_set  TEXT,
  line_start  INTEGER NOT NULL,
  language    TEXT NOT NULL,
  body_hash   TEXT
);
CREATE INDEX IF NOT EXISTS idx_reuse_finding_locations_finding ON reuse_finding_locations(finding_id);
CREATE INDEX IF NOT EXISTS idx_reuse_finding_locations_file    ON reuse_finding_locations(file_id);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""


class GraphError(RuntimeError):
    """Raised when the graph DB cannot be operated on (lock contention, etc.)."""


def open_db(
    path: Path,
    *,
    create: bool = True,
    busy_timeout_s: float = 5.0,
) -> sqlite3.Connection:
    """Open the graph DB with WAL mode + foreign keys.

    - `create=True` (default) bootstraps the schema on a fresh file.
    - `busy_timeout_s` controls how long SQLite waits when the file is locked
      by another writer (default 5s, matches the schema doc's write budget).
    - Caller is responsible for closing. Use `transaction()` for writes.
    """
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_s * 1000)}")
    if create:
        init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Apply the canonical DDL. Idempotent — uses IF NOT EXISTS everywhere."""
    conn.executescript(_SCHEMA_DDL)
    # Stamp the schema version on first init only.
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction. Rolls back on exception, commits on success.

    Raises `GraphError` if the database remains locked beyond the configured
    `busy_timeout` — surfaces concurrent-write contention as a typed error
    instead of a raw `sqlite3.OperationalError`.
    """
    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise GraphError(
                "Concurrent write timeout — outro processo escrevendo no graph.db"
            ) from exc
        raise
    try:
        yield conn
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        raise
    else:
        conn.execute("COMMIT")


def execute_many(
    conn: sqlite3.Connection,
    sql: str,
    rows: Iterable[Sequence],
) -> int:
    """Bulk insert/update helper. Returns affected row count."""
    cursor = conn.executemany(sql, list(rows))
    return cursor.rowcount


def fetch_meta(conn: sqlite3.Connection, key: str) -> str | None:
    """Read a single value from the meta key/value table."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert into the meta key/value table."""
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# TODO(wave-2): graph builder/incremental updater lives in engine/graph/.
# This module intentionally only provides plumbing — no domain logic.
