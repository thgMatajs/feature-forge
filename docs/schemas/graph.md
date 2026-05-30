# Schema — `.claude/graph.db` (SQLite)

The codebase knowledge graph. A structural map of the project that the
engine queries instead of using grep across the repo.

## Why a graph

Repeated grep is slow, lossy, and stateless. A graph:

- Indexed lookups in milliseconds (instead of seconds)
- Relationships explicit (instead of inferred each time)
- Reverse queries trivial ("who uses X")
- Incremental updates (file edit → delta, not rebuild)
- Persistent across sessions

## Why SQLite (not Kuzu, not DuckDB)

| Backend | Pros | Cons |
|---|---|---|
| **SQLite** ✅ | Ubiquitous; CLI tools; no deps; fast enough; mature | Joins for graph queries are verbose |
| Kuzu | Native graph semantics; elegant `MATCH` queries | Newer; binary dep; smaller community |
| DuckDB | Fast analytics joins | Optimized for OLAP, not point queries |

v1 picks SQLite. Migration to Kuzu is a v2 candidate if join verbosity hurts.

## Location and access

```
.claude/graph.db         # SQLite database file
```

- Created at `forge init`
- Updated incrementally via `forge ingest --event post-edit` (internal event
  router invoked by hooks — see note below)
- Rebuilt fully only by `forge init` or via menu de `forge reconfigure` →
  "rebuild do graph"
- Queryable via `forge graph` (interactive menu of named queries; SQL access
  via `forge raw query-graph` escape hatch)
- Concurrency: WAL mode + write lock for incremental updates

> **`forge ingest` is the internal event-router invoked by hooks.** It is not
> part of the 12 user-facing commands and is not typed manually. See
> `docs/design/06-command-surface.md` § "Hidden internal entrypoints".

## Tables

### `files`

```sql
CREATE TABLE files (
  id              INTEGER PRIMARY KEY,
  path            TEXT NOT NULL UNIQUE,         -- relative to repo root
  language        TEXT,                          -- kotlin | swift | typescript | ...
  module          TEXT,                          -- shared | androidApp | iosApp | webApp
  lines           INTEGER,
  last_modified   TEXT,                          -- ISO8601
  sha256          TEXT
);
CREATE INDEX idx_files_module ON files(module);
CREATE INDEX idx_files_language ON files(language);
```

### `symbols`

```sql
CREATE TABLE symbols (
  id              INTEGER PRIMARY KEY,
  file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,                 -- e.g., "LoginViewModel"
  kind            TEXT NOT NULL,                 -- class | object | interface | enum | fun | val | sealed_class
  signature       TEXT,                           -- e.g., "fun login(email: String, password: String): Flow<StateUI<LoginUI>>"
  line_start      INTEGER,
  line_end        INTEGER,
  visibility      TEXT                           -- public | internal | private | protected
);
CREATE INDEX idx_symbols_name ON symbols(name);
CREATE INDEX idx_symbols_file ON symbols(file_id);
CREATE INDEX idx_symbols_kind ON symbols(kind);
```

### `imports`

```sql
CREATE TABLE imports (
  from_file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  to_symbol       TEXT NOT NULL,                 -- fully qualified, e.g., "com.foo.Bar"
  kind            TEXT                           -- import | from | use | etc per language
);
CREATE INDEX idx_imports_from ON imports(from_file_id);
CREATE INDEX idx_imports_to ON imports(to_symbol);
```

### `features`

```sql
CREATE TABLE features (
  slug            TEXT PRIMARY KEY,
  status          TEXT NOT NULL,                 -- planned | active | done | archived
  created_at      TEXT,
  last_activity   TEXT,
  modules         TEXT                           -- JSON array of module paths
);
CREATE INDEX idx_features_status ON features(status);
```

### `screens`

```sql
CREATE TABLE screens (
  id              INTEGER PRIMARY KEY,
  feature_slug    TEXT NOT NULL REFERENCES features(slug) ON DELETE CASCADE,
  name            TEXT NOT NULL,                 -- e.g., "login"
  file_id         INTEGER REFERENCES files(id),
  route_id        INTEGER REFERENCES routes(id)
);
CREATE INDEX idx_screens_feature ON screens(feature_slug);
```

### `ds_components`

```sql
CREATE TABLE ds_components (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,          -- e.g., "MeoButton"
  level           TEXT,                           -- atom | molecule | organism | template | model
  status          TEXT,                           -- stable | beta | legacy | deprecated | planned | unknown
  path_android    TEXT,
  path_ios        TEXT,
  path_web        TEXT
);
CREATE INDEX idx_ds_components_level ON ds_components(level);
CREATE INDEX idx_ds_components_status ON ds_components(status);
```

### `ds_usage`

```sql
CREATE TABLE ds_usage (
  component_id    INTEGER NOT NULL REFERENCES ds_components(id) ON DELETE CASCADE,
  screen_id       INTEGER REFERENCES screens(id),
  file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  occurrences     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_ds_usage_component ON ds_usage(component_id);
CREATE INDEX idx_ds_usage_screen ON ds_usage(screen_id);
```

### `i18n_keys`

```sql
CREATE TABLE i18n_keys (
  id              INTEGER PRIMARY KEY,
  key             TEXT NOT NULL,                 -- e.g., "auth.login.title"
  locale          TEXT NOT NULL,                 -- pt-BR | en-US | es-ES
  value           TEXT,
  source_file_id  INTEGER REFERENCES files(id),
  UNIQUE(key, locale)
);
CREATE INDEX idx_i18n_keys_key ON i18n_keys(key);
```

### `i18n_usage`

```sql
CREATE TABLE i18n_usage (
  key_id          INTEGER NOT NULL REFERENCES i18n_keys(id) ON DELETE CASCADE,
  file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  line            INTEGER
);
CREATE INDEX idx_i18n_usage_key ON i18n_usage(key_id);
CREATE INDEX idx_i18n_usage_file ON i18n_usage(file_id);
```

### `routes`

```sql
CREATE TABLE routes (
  id              INTEGER PRIMARY KEY,
  key             TEXT NOT NULL UNIQUE,          -- e.g., "AppRoute.Login"
  params_json     TEXT,                           -- JSON list of param names
  type            TEXT,                           -- sealed_class | data_class | object
  defined_in_file INTEGER REFERENCES files(id)
);
```

### `di_graph`

```sql
CREATE TABLE di_graph (
  provider_symbol_id  INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
  consumer_symbol_id  INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
  scope               TEXT,                       -- singleton | factory | viewmodel | scoped
  kind                TEXT                        -- inject | provide | bind
);
CREATE INDEX idx_di_provider ON di_graph(provider_symbol_id);
CREATE INDEX idx_di_consumer ON di_graph(consumer_symbol_id);
```

### `tests`

```sql
CREATE TABLE tests (
  id              INTEGER PRIMARY KEY,
  file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  target_file_id  INTEGER REFERENCES files(id),  -- which production file this tests
  kind            TEXT,                           -- unit | ui | snapshot | e2e
  status          TEXT                            -- passing | failing | unknown
);
CREATE INDEX idx_tests_target ON tests(target_file_id);
CREATE INDEX idx_tests_kind ON tests(kind);
```

### `feature_commits`

```sql
CREATE TABLE feature_commits (
  feature_slug         TEXT NOT NULL REFERENCES features(slug),
  commit_sha           TEXT NOT NULL,
  files_touched_count  INTEGER,
  timestamp            TEXT,
  PRIMARY KEY (feature_slug, commit_sha)
);
```

### `task_commits`

```sql
CREATE TABLE task_commits (
  task_id              TEXT NOT NULL,             -- e.g., "lembrete-rega:TASK-0003"
  commit_sha           TEXT NOT NULL,
  files_touched_count  INTEGER,
  timestamp            TEXT,
  PRIMARY KEY (task_id, commit_sha)
);
```

### `meta`

```sql
CREATE TABLE meta (
  key                  TEXT PRIMARY KEY,
  value                TEXT
);
-- Stores: schema_version, last_full_rebuild_at, repo_sha_at_last_rebuild, etc.
```

`meta.schema_version = '1'` at v1.

## Canonical queries

The planning-conductor and sub-agents use these queries via a stable
interface. End users reach them via `forge graph` (interactive menu of named
queries); ad-hoc SQL access is intentionally available only through the
`forge raw` escape hatch — there are no flags on `forge graph`. The
`CLI form` shown under each query below is the **named-query slug** the user
picks from the interactive menu, not a flag-bearing CLI call.

### Q1 — Where is X used?

```sql
SELECT DISTINCT f.path, f.module
FROM imports i
JOIN files f ON i.from_file_id = f.id
WHERE i.to_symbol LIKE '%MeoButton';
```

CLI form: named query `where-is-used` (prompts for symbol, e.g., `MeoButton`)

### Q2 — Features structurally similar to {slug}

```sql
SELECT f.slug, f.status,
       (SELECT COUNT(*) FROM screens s WHERE s.feature_slug = f.slug) AS screens
FROM features f
WHERE f.slug != :target_slug
ORDER BY ABS(
  (SELECT COUNT(*) FROM screens WHERE feature_slug = f.slug) -
  (SELECT COUNT(*) FROM screens WHERE feature_slug = :target_slug)
);
```

CLI form: named query `similar-features` (prompts interactively for target slug, e.g., `lembrete-rega`)

### Q3 — What would break if I rename Y? (blast-radius)

```sql
SELECT f.path
FROM imports i
JOIN files f ON i.from_file_id = f.id
WHERE i.to_symbol LIKE '%' || :symbol || '%'
UNION
SELECT f.path
FROM symbols s
JOIN files f ON s.file_id = f.id
WHERE s.name LIKE '%' || :symbol || '%';
```

CLI form: named query `blast-radius` (prompts for symbol, e.g., `LoginViewModel`)

### Q4 — Screens that use component {C}

```sql
SELECT DISTINCT s.feature_slug, s.name
FROM ds_usage u
JOIN ds_components c ON u.component_id = c.id
JOIN screens s ON u.screen_id = s.id
WHERE c.name = :component;
```

CLI form: named query `screens-using` (prompts for component, e.g., `MeoCard`)

### Q5 — i18n keys not used anywhere (orphans)

```sql
SELECT k.key, k.locale
FROM i18n_keys k
LEFT JOIN i18n_usage u ON k.id = u.key_id
WHERE u.id IS NULL
GROUP BY k.key;
```

CLI form: named query `orphan-i18n-keys` (no prompt)

### Q6 — DI providers with no consumers

```sql
SELECT s.name, f.path
FROM symbols s
JOIN files f ON s.file_id = f.id
LEFT JOIN di_graph d ON d.provider_symbol_id = s.id
WHERE d.consumer_symbol_id IS NULL
  AND s.kind IN ('class', 'object');
```

CLI form: named query `orphan-di-providers` (no prompt)

### Q7 — Tests that cover {file}

```sql
SELECT t.kind, f_test.path AS test_file
FROM tests t
JOIN files f_test ON t.file_id = f_test.id
JOIN files f_target ON t.target_file_id = f_target.id
WHERE f_target.path = :file_path;
```

CLI form: named query `tests-for` (prompts for file path, e.g., `shared/feature/auth/.../LoginViewModel.kt`)

### Q8 — Feature commit history

```sql
SELECT DISTINCT fc.commit_sha, fc.timestamp
FROM feature_commits fc
WHERE fc.feature_slug = :slug
ORDER BY fc.timestamp DESC;
```

CLI form: named query `feature-history` (prompts for feature slug, e.g., `lembrete-rega`)

### Q9 — Recently modified DS components (potential breakage)

```sql
SELECT c.name, MAX(f.last_modified) AS last_modified
FROM ds_components c
JOIN files f ON f.path IN (c.path_android, c.path_ios, c.path_web)
WHERE f.last_modified > :since
GROUP BY c.name
ORDER BY last_modified DESC;
```

CLI form: named query `ds-changes-since` (prompts for date, e.g., `2026-05-01`)

### Q10 — Coverage gaps (production files without tests)

```sql
SELECT f.path
FROM files f
WHERE f.language IN ('kotlin', 'swift')
  AND f.path NOT LIKE '%Test%'
  AND f.id NOT IN (SELECT target_file_id FROM tests WHERE target_file_id IS NOT NULL);
```

CLI form: named query `untested-files` (no prompt)

## Incremental update protocol

Pseudocode for `engine/graph/incremental.py`:

```python
def on_post_edit(file_path: str):
    file_id = lookup_or_create_file(file_path)
    
    with sqlite_transaction():
        # Delete old data
        execute("DELETE FROM symbols WHERE file_id = ?", file_id)
        execute("DELETE FROM imports WHERE from_file_id = ?", file_id)
        execute("DELETE FROM i18n_usage WHERE file_id = ?", file_id)
        execute("DELETE FROM ds_usage WHERE file_id = ?", file_id)
        
        # Parse file
        parsed = parse_file(file_path)
        
        # Insert new data
        for symbol in parsed.symbols:
            insert_symbol(file_id, symbol)
        for imp in parsed.imports:
            insert_import(file_id, imp)
        for i18n_use in parsed.i18n_uses:
            insert_i18n_usage(i18n_use)
        
        # Update file metadata
        update_file_metadata(file_id, parsed.metadata)
```

Latency budget: **50-200ms per file**.

## Full rebuild protocol

When `forge init` runs, or when the user picks "rebuild do graph" no menu de
`forge reconfigure`:

```python
def full_rebuild():
    # 1. Drop all tables (DROP TABLE IF EXISTS for each)
    # 2. Re-create schema from scratch
    # 3. Walk repo, indexing files in parallel batches
    # 4. Second pass: resolve imports + relationships
    # 5. Update meta.last_full_rebuild_at
```

Latency budget: **30-60s for medium repos (~5k files); 5min cap for large**.

## Schema migrations

```python
# meta.schema_version is current
# `forge raw migrator-1-to-2` (when schema-version of graph bumps) applies a
# migration script — graph migrations follow the same escape-hatch pattern
# as workflow-config migrations.

migrations/
  001_to_002.sql       # ALTER TABLE for v1 → v2 changes
  002_to_003.sql
```

Engine refuses to operate on schema versions newer than supported (asks user
to update feature-forge first).

## Validation rules

```text
GRAPH-001  meta.schema_version must be in supported set
GRAPH-002  Every features.slug must have corresponding feature dir on disk
GRAPH-003  Every files.path must exist on disk (warn if not — orphan)
GRAPH-004  files.module values must be in workflow-config paths.feature-roots
GRAPH-005  ds_components.name must match inventory/design-system.yaml
GRAPH-006  i18n_keys.key naming must match inventory/i18n.yaml.naming.pattern
GRAPH-007  Foreign keys must resolve (no orphans)
GRAPH-008  WAL mode must be enabled
```

Run via `forge doctor` and dedicated graph checks.

## Concurrency

- **WAL mode enabled** at creation
- **One writer at a time** (lock acquired by `forge ingest`)
- **Multiple readers concurrent** (any number of `forge graph` query menu picks)
- **Writes batched** when possible (post-commit hook batches all touched
  files into one transaction)
- **Timeout per write** = 5s. If exceeded, warn and skip.

## Out of scope for v1

- Graph diff visualization
- Time-travel queries (graph state at past commit)
- Cross-repo graphs (mono-repo OK, multi-repo NO)
- Native graph semantics (Cypher / GQL) — SQL is fine for v1
- ML-based similar-feature detection (naive metrics for now)

## Related schemas

- `workflow-config.yaml` — `graph.location`, `graph.backend`, `graph.tables-enabled`
- `inventory/design-system.yaml` — source of truth for `ds_components` data
- `inventory/i18n.yaml` — source of truth for `i18n_keys` data
- Memory L1 / L2 — references graph queries to ground decisions
