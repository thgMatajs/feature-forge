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
  signature       TEXT,                          -- e.g., "fun login(email: String, password: String): Flow<StateUI<LoginUI>>"
  line_start      INTEGER,
  line_end        INTEGER,
  visibility      TEXT,                          -- public | internal | private | protected
  receiver_type   TEXT,                          -- reuse-intelligence: receiver type para extension functions
  body_hash       TEXT,                          -- reuse-intelligence: hash do body normalizado (Q12/Q15 dedup)
  body_tokens     TEXT,                          -- reuse-intelligence: tokens normalizados pra similarity
  modifiers       TEXT,                          -- reuse-intelligence: modifiers serializados (space-separated)
  body            TEXT                           -- raw source text com comentários preservados (v1.3+); ver §body column
);
CREATE INDEX idx_symbols_name          ON symbols(name);
CREATE INDEX idx_symbols_file          ON symbols(file_id);
CREATE INDEX idx_symbols_kind          ON symbols(kind);
CREATE INDEX idx_symbols_receiver_type ON symbols(receiver_type);
CREATE INDEX idx_symbols_body_hash     ON symbols(body_hash);
```

#### `symbols.body` column (v1.3+)

Texto-fonte cru do corpo do símbolo (entre `{` e `}` matched), com
comentários e whitespace preservados. Populado pra Kotlin, Swift,
TypeScript, Java e Objective-C — linguagens com corpo delimitado por
chaves. Para XML symbols, o campo é `NULL` (XML não tem corpo textual
com a mesma semântica). Body extraction reusa `_body_text._SUPPORTED_LANGS`
registry em `engine/graph/_body_text.py`.

Habilita assistentes IA a inspecionar implementação direto do graph,
sem precisar abrir o arquivo-fonte — reduz tokens de contexto e acelera
compreensão de codebases grandes.

DBs criados antes do v1.3 são migrados em-place via `ALTER TABLE symbols
ADD COLUMN body TEXT` executado idempotentemente por
`_ensure_graph_body_column` em `engine/graph/builder.py`. Re-execução
do helper em DB já migrado é no-op. SCHEMA_VERSION não é bumpado — a
migração é aditiva e backwards-compatible (queries antigas continuam
funcionando, ignorando a coluna nova). `engine/utils/sqlite_io.py`
contém apenas o DDL canônico e helpers de conexão; migrations idempotentes
vivem em `builder.py`.

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
`forge raw` escape hatch — there are no flags on `forge graph` exceto
`--json` (non-interactive JSON) e `--no-auto-build` (opt-out lazy
rebuild). O `CLI form` shown under each query below is the **named-query
slug** the user picks from the interactive menu — também aceito como
identificador via `forge graph --json`.

### forge graph --json (v1.3+)

Flag non-interactive pra consumo por IA/automação. Aceita o mesmo
conjunto de queries do menu interativo (Q1–Q17) mas emite JSON
estruturado em stdout, sem prompts. Útil pra assistentes IA consultarem
o graph antes de ler arquivos-fonte (reduz tokens de contexto).

```
forge graph --json <query> [args...]
```

Onde `<query>` é um dos formatos:
- Alias curto: `q1`, `q2`, …, `q17`, `r` (combined reuse view).
- Numeric key: `1`, `2`, …, `17`.
- Label textual do handler: `similar-features`, `blast-radius`,
  `orphan-files`, `symbols`, `ds-used-in`, `i18n-used-in`, `routes`,
  `di-deps`, `tests-for`, `commits`, `reusable-helpers`, `dup-within-module`,
  `dup-cross-module`, `kmp-migration`, `near-duplicates`,
  `redundant-platform`, `dup-ts-helpers`, `reuse-findings` (catálogo
  canônico em `_HANDLERS`, `engine/graph_cli.py:267-286`).

Output é JSON parseável (`json.loads`-válido) em stdout; stderr
reservado pra erros. Modo interactivo (`forge graph` sem `--json`)
continua disponível e inalterado.

Exemplos:

```
forge graph --json q3                                         # orphan-files (no args)
forge graph --json q4 :feature:auth                           # symbols no módulo
forge graph --json q1 lembrete-rega                           # similar-features por slug
forge graph --json q2 path/to/LoginViewModel.kt               # blast-radius (file paths posicionais)
forge graph --json blast-radius path/to/LoginViewModel.kt     # idem via label
forge graph --json r                                          # reuse-findings combined
```

Para CI/scripts determinísticos, combinar com `--no-auto-build` desativa
o lazy rebuild do graph (espera que `.claude/graph.db` já exista).

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

### Q11 — Reusable helpers (existing utilities / extensions relevant to a feature)

Returns candidate helpers (functions, including extensions) already present
in the codebase whose signature references entity types from the feature's
data contract OR live in shared utility paths (`shared/core/util/`,
`shared/core/extensions/`, `shared/feature/*/util/`). Result feeds
`tech-spec-agent` §14 reuse-existing detection — closes the gap where new
features inadvertently propose helpers that already exist.

```sql
-- Inputs: list of domain entity types from data-contract-spec.yaml
-- (e.g., ['Bonsai', 'Task', 'Reminder']) bound as :entity_n placeholders.
SELECT s.name, s.signature, s.visibility, f.path, f.module
FROM symbols s
JOIN files f ON s.file_id = f.id
WHERE s.kind = 'fun'
  AND s.visibility IN ('public', 'internal')
  AND f.module = 'shared'
  AND (
    -- Match A: signature references a domain entity type
    s.signature LIKE '%' || :entity_1 || '%'
    OR s.signature LIKE '%' || :entity_2 || '%'
    -- ...
    -- Match B: general-purpose helper in a shared utility path
    OR f.path LIKE '%/util/%'
    OR f.path LIKE '%/extensions/%'
    OR f.path LIKE '%/core/%'
  )
ORDER BY f.module, f.path, s.line_start;
```

CLI form: named query `reusable-helpers` (interactive prompt for comma-
separated entity types, e.g., `Bonsai, Task`)

Used by `planning-conductor` Phase 4.5 (between Wave B and Wave C). Result
is persisted to `.claude/memory/L1/{slug}/existing-helpers.yaml` so the
tech-spec-agent receives it in the context pack — preserves the
deterministic-context discipline (agent never queries the graph live).

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

---

## Reuse Intelligence (schema v2)

Shipped as part of `feat/reuse-intelligence-complete`. Adds detection of
duplicated code (within-module, cross-module, cross-language, near-duplicate,
redundant platform-specific) at `forge init` and on graph rebuild.

### New columns

**`files`**
- `source_set TEXT` — KMP source-set name (`commonMain`, `androidMain`,
  `iosMain`, …) or NULL for non-KMP projects.

**`symbols`**
- `receiver_type TEXT` — receiver of an extension function. Non-NULL only for
  `fun ReceiverType.name(...)` (Kotlin) and `extension Type { func name }`
  (Swift).
- `body_hash TEXT` — SHA-1[:16] of the normalized function body. NULL when
  the parser couldn't close the brace counter.
- `body_tokens TEXT` — JSON array of normalized identifiers / literals for
  cross-language Jaccard similarity.
- `modifiers TEXT` — space-separated function modifiers (`inline`, `suspend`,
  `infix`, …).

### New tables

**`module_deps`** — Gradle dependency edges parsed from each module's
`build.gradle(.kts)`:

```sql
CREATE TABLE module_deps (
  from_module TEXT NOT NULL,
  to_module   TEXT NOT NULL,
  scope       TEXT,
  PRIMARY KEY (from_module, to_module, scope)
);
```

**`reuse_findings`** — materialized output of the detection post-passes:

```sql
CREATE TABLE reuse_findings (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  category            TEXT NOT NULL,           -- 6 categories below
  group_id            TEXT NOT NULL UNIQUE,    -- SHA-256 fingerprint
  symbol_name         TEXT NOT NULL,
  receiver_type       TEXT,
  canonical_signature TEXT,
  body_hash           TEXT,
  primary_language    TEXT NOT NULL,
  modifiers           TEXT,
  suggested_target    TEXT,
  confidence          REAL NOT NULL,
  similarity_score    REAL,                    -- kmp-migration-candidate only
  detected_at         TEXT NOT NULL
);
```

`category` enum:
- `duplicate-within-module` (conf 0.95)
- `duplicate-cross-module` (conf 0.85)
- `redundant-platform-specific` (conf 0.90)
- `near-duplicate` (conf 0.40 — manual review)
- `kmp-migration-candidate` (conf 0.50–0.75 scaled by similarity)
- `duplicate-ts-helper` (conf 0.95)

`group_id` is a 64-char SHA-256 fingerprint compatible with the distiller's
rejection veto. Stable across rebuilds.

**`reuse_finding_locations`** — one row per (finding, file) pair:

```sql
CREATE TABLE reuse_finding_locations (
  finding_id  INTEGER NOT NULL REFERENCES reuse_findings(id) ON DELETE CASCADE,
  file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  module      TEXT NOT NULL,
  source_set  TEXT,
  line_start  INTEGER NOT NULL,
  language    TEXT NOT NULL,
  body_hash   TEXT
);
```

### Canonical queries Q12–Q17

| Q   | Function                            | Category                       |
|-----|-------------------------------------|--------------------------------|
| Q12 | `find_duplicates_within_module`     | `duplicate-within-module`      |
| Q13 | `find_duplicates_cross_module`      | `duplicate-cross-module`       |
| Q14 | `find_kmp_migration_candidates`     | `kmp-migration-candidate`      |
| Q15 | `find_near_duplicates`              | `near-duplicate`               |
| Q16 | `find_redundant_platform_specific`  | `redundant-platform-specific`  |
| Q17 | `find_duplicate_ts_helpers`         | `duplicate-ts-helper`          |

Plus `list_reuse_findings(category=None)` reads the materialized table.

### Signature normalization

Canonical form: `[Receiver.]fun([type1, type2, ...]): return_type` (Kotlin)
or `[Receiver.]func([type1, type2, ...]) [effects] -> return_type` (Swift).
Parameter names dropped; types preserved; generic bounds simplified
(`<T : Any, U>` → `<T, U>`); modifiers tracked in `symbols.modifiers`.

### Body normalization

Line + block comments stripped; whitespace collapsed; identifiers / operators
/ literals preserved verbatim. Hash = first 16 hex chars of `sha1(normalized)`.

### Cross-language similarity (Q14)

Body tokens are identifiers + numeric / string literals, lowercased and
filtered against a per-language noise list (`val`/`fun` for Kotlin,
`let`/`func` for Swift, `let`/`function` for TS). Jaccard similarity gates:

- ≥ 0.80 → confidence 0.75
- 0.60–0.80 → 0.60
- 0.40–0.60 → 0.50
- < 0.40 → dropped

### Module + source-set inference

`engine/graph/gradle_modules.py` parses `settings.gradle(.kts)` for
`include(":...")` declarations and maps file paths to Gradle modules via
**longest-prefix match**. Falls back to first path segment for mono-module
projects. Source-set detected from path against the curated KMP set
(`commonMain`, `androidMain`, `iosMain`, …).

### Q11 backward compatibility

`find_reusable_helpers` previously filtered `f.module = 'shared'`. With
multi-module shared (`shared:core`, `shared:feature:auth`, ...) the filter
became `f.module = 'shared' OR f.module LIKE 'shared:%'`. Single-module
projects keep working.
