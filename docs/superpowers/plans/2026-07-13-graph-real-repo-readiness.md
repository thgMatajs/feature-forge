# GRAPH-REAL-REPO Stage 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the codebase graph buildable and platform-aware on a production mobile monorepo — `_resolve_import_targets` completes in ~O(imports + symbols), and a new `files.platform` column drives the platform-specific reuse queries.

**Architecture:** Two independent fixes. **Fix A** replaces the correlated `LIKE '%.'||s.name` subquery in `_resolve_import_targets` (currently ~O(imports × symbols)) with a single-pass in-memory `name → (path, file_id)` index; the edge set is provably preserved by an equivalence test that runs the legacy SQL as an oracle on a controlled fixture. **Fix B** adds a `files.platform` column (`{common, android, ios, jvm, NULL}`) via idempotent ALTER + canonical DDL (no `SCHEMA_VERSION` bump), populated by a new `infer_platform(...)` helper on both the full-build and incremental insert paths, then rewires the two platform-specific reuse queries (`redundant-platform-specific`, `kmp-migration-candidate`) to discriminate by `files.platform` instead of the `module LIKE 'androidApp%'` + literal `source_set` heuristic.

**Tech Stack:** Python 3.13, stdlib `sqlite3`, `pathspec` (already vendored). Tests via `.venv/bin/pytest`. No new dependencies.

## Global Constraints

- **Dependencies:** stdlib + `pathspec` only. NO new external dependency.
- **`SCHEMA_VERSION` stays `"2"`** (`engine/utils/sqlite_io.py:24`). The new column is added exactly like `body`/`source_set` were: canonical DDL for fresh DBs + idempotent `ALTER TABLE` for legacy DBs. Do NOT bump it.
- **Behavior-preserving perf fix:** Fix A must resolve the SAME set of `(from_file_id, to_file_id)` edges as the current algorithm. The equivalence test is the guard.
- **Canonical test runner is `.venv/bin/pytest`** — the system `pytest` lacks `json5`/deps and gives false negatives. Every command below uses `.venv/bin/pytest`.
- **TDD mandatory:** each code task writes a FAILING test first, runs it to confirm RED, writes minimal impl, runs it GREEN, commits.
- **Atomic commits, repo message style:** `fix(graph): …`, `feat(graph): …`, `perf(graph): …`.
- **Doc-sync in the SAME commit** (Mandamento #6): any commit touching `engine/**` also updates `CHANGELOG.md` (`## [Unreleased]`) and, when the schema changes, `docs/schemas/graph.md`.
- **Scope is STRICTLY Stage 1.** Do NOT broaden the symbol universe (composables/members/classes), do NOT add fuzzy similarity, do NOT integrate into any consumer repo. Those are Stage 2/3 and are gated on the re-spike.
- **Voice:** code comments follow the repo's mentor-calmo, pt-BR convention (see neighboring comments in `engine/graph/*.py`).

---

## File Structure

**Modified (by the executor — this plan is a doc only):**
- `engine/graph/builder.py` — rewrite `_resolve_import_targets` (Task 1); add `_ensure_platform_column` + wire into `build_full` migration block (Task 2); add `platform` to the `_ingest_file` INSERT (Task 4).
- `engine/graph/gradle_modules.py` — add `infer_platform(...)` helper + platform mapping tables (Task 3).
- `engine/graph/incremental.py` — import `_ensure_platform_column` + `infer_platform`; wire the column migration into `_apply_ensure_migrations`; bump `_MIGRATIONS_KEY`; add `platform` to the `_refresh_file` INSERT (Tasks 2 & 4).
- `engine/graph/duplicates.py` — rewrite `_q_redundant_platform_specific` + `_q_kmp_migration_candidates` WHERE clauses to use `files.platform` (Task 5).
- `engine/graph/queries.py` — rewrite `find_redundant_platform_specific` + `find_kmp_migration_candidates` WHERE clauses to use `files.platform` (Task 5).
- `engine/utils/sqlite_io.py` — add `platform TEXT` + index to the canonical `files` DDL (Task 2).
- `docs/schemas/graph.md` — document the `platform` column + inference (Task 2).
- `CHANGELOG.md` — `## [Unreleased]` entries (every engine-touching commit).

**New test files (by the executor):**
- `tests/unit/test_resolve_import_targets_equivalence.py` (Task 1)
- `tests/unit/test_files_platform_column.py` (Task 2)
- `tests/unit/test_infer_platform.py` (Task 3)
- `tests/unit/test_platform_populated_build_and_incremental.py` (Task 4)
- `tests/unit/test_platform_aware_reuse_queries.py` (Task 5)

**Dependency order:** Task 1 is fully independent. Task 3 (pure helper) is independent. Task 2 (schema) must precede Tasks 4 and 5 (they reference `files.platform`). Task 4 depends on Tasks 2 + 3. Task 5 depends on Task 2 (and is validated end-to-end by Task 4's population, but its unit test hand-seeds `platform` so it is independently testable once the column exists).

---

## Task 1: Rewrite `_resolve_import_targets` to ~O(imports + symbols)

**Files:**
- Modify: `engine/graph/builder.py:1078-1104` (the `_resolve_import_targets` function body)
- Modify: `CHANGELOG.md` (`## [Unreleased] > ### Fixed`)
- Test: `tests/unit/test_resolve_import_targets_equivalence.py` (create)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `_resolve_import_targets(conn: sqlite3.Connection) -> None` — SAME signature as today. Callers (`builder.build_full` @ line 157, `incremental.update_file` @ line 139, `incremental.update_batch` @ line 226) are unchanged.

**Current behavior to preserve (read before editing).** The current body (`engine/graph/builder.py:1090-1104`) is:

```python
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
```

Semantics: for every `imports` row whose `to_file_id IS NULL`, find candidate symbols where `s.name == to_symbol` (exact) OR `to_symbol` ends with `"." + s.name` (suffix), join to their owning file, order by `(f.path, s.name)` ascending, take the first, and set `to_file_id` to that symbol's `file_id`. No match → stays `NULL`. Rows already resolved are untouched. `imports` has no explicit primary key; use the implicit `rowid`.

- [ ] **Step 1: Write the equivalence + scale test (RED)**

Create `tests/unit/test_resolve_import_targets_equivalence.py`. The test embeds the legacy SQL as an oracle: it computes the reference `{rowid: to_file_id}` map with the old query on a controlled fixture, resets `to_file_id` to NULL, runs the new `_resolve_import_targets`, and asserts the maps are identical. A second test asserts the resolver stays fast and correct at scale.

```python
"""Equivalence + scale guard for the rewritten `_resolve_import_targets`.

Fix A (GRAPH-REAL-REPO Stage 1) replaced the correlated `LIKE '%.'||s.name`
subquery with an in-memory `name -> (path, file_id)` index. The edge set MUST
be identical to the legacy algorithm — this test embeds the legacy SQL as an
oracle so any divergence is caught on a controlled fixture.
"""

from __future__ import annotations

import time
from pathlib import Path

from engine.graph.builder import _resolve_import_targets
from engine.utils.sqlite_io import open_db, transaction

# Verbatim copy of the legacy resolution query (used ONLY as the test oracle).
_LEGACY_SQL = """
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


def _add_file(conn, path: str) -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language) VALUES (?, 'kotlin')", (path,)
    )
    return cur.lastrowid


def _add_symbol(conn, file_id: int, name: str) -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind) VALUES (?, ?, 'class')",
        (file_id, name),
    )


def _add_import(conn, from_file_id: int, to_symbol: str) -> None:
    conn.execute(
        "INSERT INTO imports(from_file_id, to_symbol, kind, to_file_id) "
        "VALUES (?, ?, 'import', NULL)",
        (from_file_id, to_symbol),
    )


def _snapshot(conn) -> dict[int, int | None]:
    return {
        row["rowid"]: row["to_file_id"]
        for row in conn.execute(
            "SELECT rowid, to_file_id FROM imports"
        ).fetchall()
    }


def _build_fixture(conn) -> None:
    # Same symbol name "Bar" in three files with deterministic path ordering;
    # ORDER BY f.path must pick "a/Aardvark.kt".
    f_aard = _add_file(conn, "a/Aardvark.kt")
    f_alpha = _add_file(conn, "a/Alpha.kt")
    f_beta = _add_file(conn, "b/Beta.kt")
    f_gamma = _add_file(conn, "c/Gamma.kt")
    consumer = _add_file(conn, "z/Consumer.kt")
    _add_symbol(conn, f_aard, "Bar")
    _add_symbol(conn, f_alpha, "Bar")
    _add_symbol(conn, f_beta, "Bar")
    _add_symbol(conn, f_gamma, "Widget")
    # Suffix match, exact match, no-match, bare-name match.
    _add_import(conn, consumer, "com.x.Bar")     # -> f_aard (min path)
    _add_import(conn, consumer, "Widget")        # -> f_gamma (exact)
    _add_import(conn, consumer, "com.NoSuch")    # -> NULL (unresolved)
    _add_import(conn, consumer, "Bar")           # -> f_aard (min path)


def test_resolver_matches_legacy_on_controlled_fixture(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            _build_fixture(conn)
        # 1. Oracle: run the legacy SQL, snapshot, then reset.
        with transaction(conn):
            conn.execute(_LEGACY_SQL)
        oracle = _snapshot(conn)
        with transaction(conn):
            conn.execute("UPDATE imports SET to_file_id = NULL")
        # 2. New algorithm.
        with transaction(conn):
            _resolve_import_targets(conn)
        actual = _snapshot(conn)
        assert actual == oracle
        # Sanity: the fixture actually resolved something and left one NULL.
        assert sum(1 for v in actual.values() if v is None) == 1
        assert sum(1 for v in actual.values() if v is not None) == 3
    finally:
        conn.close()


def test_resolver_scale_smoke(tmp_path: Path) -> None:
    db = tmp_path / "scale.db"
    conn = open_db(db, create=True)
    n = 3000
    try:
        with transaction(conn):
            consumer = _add_file(conn, "zzz/Consumer.kt")
            for i in range(n):
                fid = _add_file(conn, f"pkg/File{i:05d}.kt")
                _add_symbol(conn, fid, f"Sym{i:05d}")
                _add_import(conn, consumer, f"com.example.Sym{i:05d}")
        started = time.perf_counter()
        with transaction(conn):
            _resolve_import_targets(conn)
        elapsed = time.perf_counter() - started
        resolved = conn.execute(
            "SELECT COUNT(*) AS c FROM imports WHERE to_file_id IS NOT NULL"
        ).fetchone()["c"]
        assert resolved == n
        # Generous bound: the O(n^2) version would blow past this for n=3000.
        assert elapsed < 10.0, f"resolver too slow: {elapsed:.2f}s"
    finally:
        conn.close()
```

- [ ] **Step 2: Run the test to verify it fails (RED)**

Run: `.venv/bin/pytest tests/unit/test_resolve_import_targets_equivalence.py -v`
Expected: both tests PASS against the current code (the current algorithm already produces the oracle result and n=3000 is small enough to finish under 10s). This test is a **guard**, not a red-first behavior test — the rewrite must keep it green. Confirm both pass now, then proceed. (If either fails on current code, stop and reconcile the fixture with actual semantics before touching `builder.py`.)

- [ ] **Step 3: Rewrite `_resolve_import_targets` (minimal impl)**

Replace the `conn.execute(""" UPDATE imports ... """)` block (`engine/graph/builder.py:1090-1104`) with the single-pass index algorithm. Keep the docstring lines 1079-1089 (update the wording to describe the index). New body:

```python
    # F-perf (GRAPH-REAL-REPO Stage 1): o loop correlacionado
    # `LIKE '%.'||s.name` era O(imports × symbols) (wildcard à esquerda,
    # não-indexável) e não completava em monorepo real. Trocado por um
    # índice em memória `name -> (menor path, file_id)` (uma passada sobre
    # symbols) + resolução por segmento terminal. Semântica preservada: o
    # mesmo critério exato/sufixo e o mesmo desempate ORDER BY (f.path,
    # s.name) — ver test_resolve_import_targets_equivalence.
    best_by_name: dict[str, tuple[str, int]] = {}
    for row in conn.execute(
        "SELECT s.name AS name, s.file_id AS file_id, f.path AS path "
        "FROM symbols s JOIN files f ON s.file_id = f.id"
    ):
        name = row["name"]
        path = row["path"]
        prev = best_by_name.get(name)
        if prev is None or path < prev[0]:
            best_by_name[name] = (path, row["file_id"])

    updates: list[tuple[int, int]] = []
    for row in conn.execute(
        "SELECT rowid AS rid, to_symbol AS to_symbol "
        "FROM imports WHERE to_file_id IS NULL"
    ).fetchall():
        target = row["to_symbol"]
        if target is None:
            continue
        # Candidate symbol names = exact target + every dot-suffix tail,
        # mirroring `s.name = to_symbol OR to_symbol LIKE '%.' || s.name`.
        candidates = [target]
        for pos, ch in enumerate(target):
            if ch == ".":
                candidates.append(target[pos + 1:])
        best: tuple[str, str, int] | None = None  # (path, name, file_id)
        for name in candidates:
            entry = best_by_name.get(name)
            if entry is None:
                continue
            cand = (entry[0], name, entry[1])
            if best is None or (cand[0], cand[1]) < (best[0], best[1]):
                best = cand
        if best is not None:
            updates.append((best[2], row["rid"]))

    if updates:
        conn.executemany(
            "UPDATE imports SET to_file_id = ? WHERE rowid = ?", updates
        )
```

Note: `best_by_name[name]` keeps the lexicographically smallest `path` for that symbol name — that is the `ORDER BY f.path` winner; the secondary `s.name` sort is applied across the candidate-name set per import. This reproduces the legacy `ORDER BY f.path, s.name LIMIT 1` exactly (two symbols sharing the same min path also share the same `file_id`, so the tie is immaterial).

- [ ] **Step 4: Run the test to verify it passes (GREEN)**

Run: `.venv/bin/pytest tests/unit/test_resolve_import_targets_equivalence.py -v`
Expected: `2 passed`.

- [ ] **Step 5: Run the broader graph lane to confirm no regression**

Run: `.venv/bin/pytest tests/unit/test_graph_builder.py tests/unit/test_reuse_intelligence.py tests/engine/graph -q`
Expected: all pass (no count regression vs. baseline).

- [ ] **Step 6: Add CHANGELOG entry**

In `CHANGELOG.md` under `## [Unreleased] > ### Fixed`, add:

```markdown
- **`_resolve_import_targets` — perf O(imports+symbols) (GRAPH-REAL-REPO Stage 1):** troca o subquery correlacionado `LIKE '%.'||s.name` (O(imports×symbols), não completava em monorepo real ~18k arquivos) por um índice em memória `name → (menor path, file_id)` + resolução por segmento terminal. Semântica de resolução de edges preservada (test de equivalência com a SQL legada como oráculo num fixture controlado). `forge init`/rebuild deixa de travar na escala de produção.
```

- [ ] **Step 7: Commit**

```bash
git add engine/graph/builder.py tests/unit/test_resolve_import_targets_equivalence.py CHANGELOG.md
git commit -m "perf(graph): resolve import targets em O(imports+symbols) via índice em memória"
```

---

## Task 2: Add the `files.platform` column (schema + migration, no population yet)

**Files:**
- Modify: `engine/utils/sqlite_io.py:29-42` (canonical `files` DDL + indexes)
- Modify: `engine/graph/builder.py` — add `_ensure_platform_column` (next to the other `_ensure_*`, ~line 1130) + call it in the `build_full` migration block (`engine/graph/builder.py:104-106`)
- Modify: `engine/graph/incremental.py:19-36` (import `_ensure_platform_column`), `:56` (bump `_MIGRATIONS_KEY`), `:104-107` (call `_ensure_platform_column` in `_apply_ensure_migrations`)
- Modify: `docs/schemas/graph.md:49-71` (files DDL + note)
- Modify: `CHANGELOG.md`
- Test: `tests/unit/test_files_platform_column.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `_ensure_platform_column(conn: sqlite3.Connection) -> None` (in `engine/graph/builder.py`), imported by `incremental.py`. New column `files.platform TEXT` + index `idx_files_platform`. Bumped marker `_MIGRATIONS_KEY = "migrations_applied_v1_4"`.

**Why the marker bump matters.** `incremental._apply_ensure_migrations` (`engine/graph/incremental.py:102-103`) short-circuits when the `meta` marker `_MIGRATIONS_KEY` is already stamped. A legacy DB stamped under `"migrations_applied_v1_3"` would SKIP the new `ALTER TABLE`, so the incremental insert (Task 4) would hit a missing column. Bumping the key to `"migrations_applied_v1_4"` forces the `_ensure_*` chain (all idempotent) to re-run once, adding the column. `build_full` calls the `_ensure_*` chain directly (no marker gate), so it is unaffected either way.

- [ ] **Step 1: Write the migration test (RED)**

Create `tests/unit/test_files_platform_column.py`:

```python
"""Schema guard — `files.platform` column (GRAPH-REAL-REPO Stage 1, no bump)."""

from __future__ import annotations

from pathlib import Path

from engine.graph import incremental
from engine.graph.builder import _ensure_platform_column, build_full
from engine.utils.sqlite_io import open_db


def _platform_columns(conn) -> set[str]:
    return {c["name"] for c in conn.execute("PRAGMA table_info(files)").fetchall()}


def test_fresh_db_ddl_has_platform_column(tmp_path: Path) -> None:
    # open_db(create=True) runs the canonical DDL from sqlite_io.
    conn = open_db(tmp_path / "fresh.db", create=True)
    try:
        assert "platform" in _platform_columns(conn)
        idx = {r["name"] for r in conn.execute(
            "PRAGMA index_list(files)"
        ).fetchall()}
        assert "idx_files_platform" in idx
    finally:
        conn.close()


def test_ensure_platform_column_is_idempotent(tmp_path: Path) -> None:
    conn = open_db(tmp_path / "legacy.db", create=True)
    try:
        # Simulate a legacy DB that predates the canonical DDL change.
        conn.execute("DROP INDEX IF EXISTS idx_files_platform")
        try:
            conn.execute("ALTER TABLE files DROP COLUMN platform")
        except Exception:
            pass
        assert "platform" not in _platform_columns(conn)
        _ensure_platform_column(conn)
        assert "platform" in _platform_columns(conn)
        # Second call must be a no-op (no exception).
        _ensure_platform_column(conn)
        assert "platform" in _platform_columns(conn)
    finally:
        conn.close()


def test_build_full_creates_platform_column(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "A.kt").write_text("package x\nclass A\n", encoding="utf-8")
    db = proj / "graph.db"
    build_full(proj, db_path=db)
    conn = open_db(db, create=False)
    try:
        assert "platform" in _platform_columns(conn)
    finally:
        conn.close()


def test_incremental_migration_adds_column_despite_stale_marker(
    tmp_path: Path,
) -> None:
    """A DB stamped with the OLD marker must still gain `platform`."""
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    f = proj / "src" / "A.kt"
    f.write_text("package x\nclass A\n", encoding="utf-8")
    db = proj / "graph.db"
    conn = open_db(db, create=True)
    try:
        # Drop the column and stamp the STALE marker to prove the bump works.
        conn.execute("DROP INDEX IF EXISTS idx_files_platform")
        try:
            conn.execute("ALTER TABLE files DROP COLUMN platform")
        except Exception:
            pass
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) "
            "VALUES ('migrations_applied_v1_3', '1')"
        )
        conn.commit()
    finally:
        conn.close()
    incremental.update_file(proj, f, db_path=db)
    conn = open_db(db, create=False)
    try:
        assert "platform" in _platform_columns(conn)
    finally:
        conn.close()
```

- [ ] **Step 2: Run the test to verify it fails (RED)**

Run: `.venv/bin/pytest tests/unit/test_files_platform_column.py -v`
Expected: FAIL — `ImportError: cannot import name '_ensure_platform_column'` (function does not exist yet) / column-missing assertions.

- [ ] **Step 3a: Add `platform` to the canonical DDL**

In `engine/utils/sqlite_io.py`, edit the `files` DDL (lines 29-42). Add the column after `source_set` and an index after `idx_files_source_set`:

```sql
CREATE TABLE IF NOT EXISTS files (
  id              INTEGER PRIMARY KEY,
  path            TEXT NOT NULL UNIQUE,
  language        TEXT,
  module          TEXT,
  source_set      TEXT,
  platform        TEXT,
  lines           INTEGER,
  last_modified   TEXT,
  sha256          TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_module     ON files(module);
CREATE INDEX IF NOT EXISTS idx_files_language   ON files(language);
CREATE INDEX IF NOT EXISTS idx_files_source_set ON files(source_set);
CREATE INDEX IF NOT EXISTS idx_files_platform   ON files(platform);
```

- [ ] **Step 3b: Add `_ensure_platform_column` to `builder.py`**

Insert a new function immediately after `_ensure_reuse_intelligence_columns` (i.e., after `engine/graph/builder.py:1210`), mirroring the idempotent ALTER + index pattern:

```python
def _ensure_platform_column(conn: sqlite3.Connection) -> None:
    """Migration: add ``files.platform TEXT`` + index for legacy DBs (schema v2).

    Plataforma derivada (``common`` | ``android`` | ``ios`` | ``jvm`` | NULL)
    via ``infer_platform``. Adicionada por ALTER idempotente — mesmo padrão do
    ``source_set`` — sem bump de SCHEMA_VERSION; DBs novos já recebem a coluna
    do DDL canônico em ``engine/utils/sqlite_io.py``.
    """
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(files)").fetchall()}
    if "platform" not in cols:
        conn.execute("ALTER TABLE files ADD COLUMN platform TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_platform ON files(platform)")
```

- [ ] **Step 3c: Wire it into `build_full`'s migration block**

In `engine/graph/builder.py`, edit the migration block (lines 103-106) to add the new call:

```python
        try:
            _ensure_imports_to_file_id_column(conn)
            _ensure_reuse_intelligence_columns(conn)
            _ensure_graph_body_column(conn)
            _ensure_platform_column(conn)
        except sqlite3.Error as exc:
```

- [ ] **Step 3d: Wire it into the incremental path + bump the marker**

In `engine/graph/incremental.py`, add `_ensure_platform_column` to the `from engine.graph.builder import (...)` block (lines 19-36, keep alphabetical-ish grouping near the other `_ensure_*`):

```python
from engine.graph.builder import (
    _LANGUAGE_EXTENSIONS,
    _ensure_graph_body_column,
    _ensure_imports_to_file_id_column,
    _ensure_platform_column,
    _ensure_reuse_intelligence_columns,
    _infer_feature_slug,
    ...
)
```

Bump the marker (line 56):

```python
_MIGRATIONS_KEY = "migrations_applied_v1_4"
```

Add the call inside `_apply_ensure_migrations` (the `try` block at lines 104-107):

```python
    try:
        _ensure_imports_to_file_id_column(conn)
        _ensure_reuse_intelligence_columns(conn)
        _ensure_graph_body_column(conn)
        _ensure_platform_column(conn)
    except sqlite3.OperationalError as exc:
```

- [ ] **Step 4: Run the test to verify it passes (GREEN)**

Run: `.venv/bin/pytest tests/unit/test_files_platform_column.py -v`
Expected: `4 passed`.

- [ ] **Step 5: Doc-sync — schema doc**

In `docs/schemas/graph.md`, edit the `files` DDL block (lines 49-63) to add the column + index, and add a note after the existing `source_set` note (lines 68-71):

```sql
CREATE TABLE files (
  id              INTEGER PRIMARY KEY,
  path            TEXT NOT NULL UNIQUE,         -- relative to repo root
  language        TEXT,                          -- kotlin | swift | typescript | java | objc | xml | ...
  module          TEXT,                          -- shared | androidApp | iosApp | webApp
  source_set      TEXT,                          -- KMP source-set (commonMain | androidMain | iosMain | …) — NULL fora de KMP
  platform        TEXT,                          -- plataforma derivada: common | android | ios | jvm — NULL quando indeterminado
  lines           INTEGER,
  last_modified   TEXT,                          -- ISO8601
  sha256          TEXT
);
CREATE INDEX idx_files_module ON files(module);
CREATE INDEX idx_files_language ON files(language);
CREATE INDEX idx_files_source_set ON files(source_set);
CREATE INDEX idx_files_platform ON files(platform);
```

Add note text:

```markdown
> **`files.platform`** (GRAPH-REAL-REPO Stage 1) é a plataforma *derivada* do
> arquivo — distinta de `source_set` (o nome literal do source-set KMP). Vem
> de `infer_platform(module, source_set, rel_path, language)`
> (`engine/graph/gradle_modules.py`): source-set KMP explícito mapeia direto
> (`commonMain→common`, `androidMain/androidTest/androidUnitTest→android`,
> `iosMain`/variantes iOS`→ios`, `jvmMain→jvm`); sem source-set KMP, Swift/ObjC
> → `ios`, `.java` → `android`, e Kotlin/XML sob um dir `src/<sourceSet>/`
> (layout Android/JVM padrão, ex.: `/src/main/`) → `android`. Casos sem sinal
> (js/wasm/native, flavors custom) ficam `NULL` (degrade seguro — as queries
> plataforma-específicas ignoram `NULL`). Aparece no DDL canônico
> (`engine/utils/sqlite_io.py`) + ALTER idempotente para DBs legados; SEM bump
> de `SCHEMA_VERSION` (mesmo padrão de `body`/`source_set`).
```

- [ ] **Step 6: CHANGELOG entry**

In `CHANGELOG.md` under `## [Unreleased] > ### Added`:

```markdown
- **Coluna `files.platform` (GRAPH-REAL-REPO Stage 1):** plataforma derivada (`common`|`android`|`ios`|`jvm`|NULL) adicionada via DDL canônico + ALTER idempotente (`_ensure_platform_column`), SEM bump de `SCHEMA_VERSION`. Marker de migração incremental bumpado `migrations_applied_v1_3` → `migrations_applied_v1_4` para DBs legados aplicarem o ALTER no path incremental.
```

- [ ] **Step 7: Commit**

```bash
git add engine/utils/sqlite_io.py engine/graph/builder.py engine/graph/incremental.py docs/schemas/graph.md CHANGELOG.md tests/unit/test_files_platform_column.py
git commit -m "feat(graph): coluna files.platform via ALTER idempotente (sem bump de schema)"
```

---

## Task 3: `infer_platform(...)` helper

**Files:**
- Modify: `engine/graph/gradle_modules.py` (add mapping tables + `infer_platform`, after `infer_module_and_source_set` @ line 121)
- Modify: `CHANGELOG.md`
- Test: `tests/unit/test_infer_platform.py` (create)

**Interfaces:**
- Consumes: nothing (pure function).
- Produces: `infer_platform(module: str, source_set: Optional[str], rel_path: str, language: str) -> Optional[str]` returning one of `"common" | "android" | "ios" | "jvm" | None`. Consumed by `builder._ingest_file` and `incremental._refresh_file` (Task 4).

**Rules (AC-2):**
1. KMP source-set present → map via a fixed table (`commonMain→common`, `androidMain`/`androidTest`/`androidUnitTest→android`, `iosMain`/`iosTest`/`iosArm64Main`/`iosSimulatorArm64Main`/`iosX64Main`/`appleMain→ios`, `jvmMain`/`jvmTest→jvm`). A source-set present but NOT in the map (`jsMain`, `wasmJsMain`, `nativeMain`) → `None`.
2. No KMP source-set: `swift`/`objc` → `ios`; `java` → `android`; `kotlin`/`xml` under a `src/<sourceSet>/` dir → `android`; else → `None`.

- [ ] **Step 1: Write the table-driven test (RED)**

Create `tests/unit/test_infer_platform.py`:

```python
"""Table-driven coverage for `infer_platform` (GRAPH-REAL-REPO Stage 1)."""

from __future__ import annotations

import pytest

from engine.graph.gradle_modules import infer_platform


@pytest.mark.parametrize(
    "module, source_set, rel_path, language, expected",
    [
        # 1. KMP source-set explicit -> mapped platform.
        ("shared", "commonMain", "shared/src/commonMain/kotlin/A.kt", "kotlin", "common"),
        ("shared", "commonTest", "shared/src/commonTest/kotlin/A.kt", "kotlin", "common"),
        ("shared", "androidMain", "shared/src/androidMain/kotlin/A.kt", "kotlin", "android"),
        ("shared", "androidUnitTest", "shared/src/androidUnitTest/kotlin/A.kt", "kotlin", "android"),
        ("shared", "androidTest", "shared/src/androidTest/kotlin/A.kt", "kotlin", "android"),
        ("shared", "iosMain", "shared/src/iosMain/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "iosArm64Main", "shared/src/iosArm64Main/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "iosSimulatorArm64Main", "shared/src/iosSimulatorArm64Main/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "iosX64Main", "shared/src/iosX64Main/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "appleMain", "shared/src/appleMain/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "jvmMain", "shared/src/jvmMain/kotlin/A.kt", "kotlin", "jvm"),
        # KMP source-set present but not in {android,ios,common,jvm} -> None.
        ("shared", "jsMain", "shared/src/jsMain/kotlin/A.kt", "kotlin", None),
        ("shared", "wasmJsMain", "shared/src/wasmJsMain/kotlin/A.kt", "kotlin", None),
        ("shared", "nativeMain", "shared/src/nativeMain/kotlin/A.kt", "kotlin", None),
        # 2. No KMP source-set -> language/path inference.
        ("app", None, "app/src/main/kotlin/com/x/Foo.kt", "kotlin", "android"),
        ("app", None, "app/src/debug/kotlin/com/x/Foo.kt", "kotlin", "android"),
        ("app", None, "app/src/main/res/layout/foo.xml", "xml", "android"),
        ("core", None, "core/src/main/java/com/x/Legacy.java", "java", "android"),
        ("androidApp", None, "androidApp/src/main/kotlin/com/x/Foo.kt", "kotlin", "android"),
        ("iosApp", None, "iosApp/Sources/HomeView.swift", "swift", "ios"),
        ("iosApp", None, "iosApp/Legacy.m", "objc", "ios"),
        # Java is always android even without a src/ dir.
        ("root", None, "tools/Gen.java", "java", "android"),
        # 3. No signal -> None.
        ("root", None, "scripts/build.gradle.kts", "kotlin", None),
        ("root", None, "docs/readme.ts", "typescript", None),
    ],
)
def test_infer_platform_table(module, source_set, rel_path, language, expected):
    assert infer_platform(module, source_set, rel_path, language) == expected
```

- [ ] **Step 2: Run the test to verify it fails (RED)**

Run: `.venv/bin/pytest tests/unit/test_infer_platform.py -v`
Expected: FAIL — `ImportError: cannot import name 'infer_platform'`.

- [ ] **Step 3: Implement `infer_platform`**

In `engine/graph/gradle_modules.py`, add after `infer_module_and_source_set` (after line 121). The `re` module is already imported (line 16):

```python
# Plataforma derivada por source-set KMP explícito. Source-sets fora deste
# mapa (jsMain / wasmJsMain / nativeMain) não têm plataforma mobile-nativa
# e caem em NULL (degrade seguro).
_KMP_PLATFORM_BY_SOURCE_SET: dict[str, str] = {
    "commonMain": "common",
    "commonTest": "common",
    "androidMain": "android",
    "androidTest": "android",
    "androidUnitTest": "android",
    "iosMain": "ios",
    "iosTest": "ios",
    "iosArm64Main": "ios",
    "iosSimulatorArm64Main": "ios",
    "iosX64Main": "ios",
    "appleMain": "ios",
    "jvmMain": "jvm",
    "jvmTest": "jvm",
}

# Diretório de source-set Gradle não-KMP (layout Android/JVM padrão):
# `.../src/<algo>/...` (ex.: `/src/main/`, `/src/debug/`, `/src/release/`).
_SRC_SOURCESET_RE = re.compile(r"(?:^|/)src/[^/]+/")


def infer_platform(
    module: str,
    source_set: Optional[str],
    rel_path: str,
    language: str,
) -> Optional[str]:
    """Derive a file's platform: ``common`` | ``android`` | ``ios`` | ``jvm`` | None.

    Distinta de ``source_set`` (nome literal do source-set KMP): ``platform`` é
    a plataforma *derivada*, para que as reuse-queries enxerguem código
    Android em ``/src/main/`` e Swift em layout Xcode, não só naming KMP.

    - Source-set KMP explícito → plataforma mapeada (``commonMain→common`` etc.).
      Source-sets sem plataforma mobile (``jsMain``/``wasmJsMain``/``nativeMain``)
      → ``None``.
    - Sem source-set KMP: Swift/ObjC → ``ios``; ``.java`` → ``android``;
      Kotlin/XML sob um dir ``src/<sourceSet>/`` (layout Android/JVM padrão)
      → ``android``.
    - Caso contrário → ``None`` (degrade seguro; queries ignoram NULL).
    """
    if source_set is not None:
        return _KMP_PLATFORM_BY_SOURCE_SET.get(source_set)

    rel = rel_path.replace("\\", "/")
    if language in ("swift", "objc"):
        return "ios"
    if language == "java":
        return "android"
    if language in ("kotlin", "xml") and _SRC_SOURCESET_RE.search(rel):
        return "android"
    return None
```

- [ ] **Step 4: Run the test to verify it passes (GREEN)**

Run: `.venv/bin/pytest tests/unit/test_infer_platform.py -v`
Expected: all parametrized cases pass.

- [ ] **Step 5: CHANGELOG entry**

Append to the same `## [Unreleased] > ### Added` bullet family (or add a sub-line under the Task 2 platform bullet):

```markdown
- **`infer_platform(module, source_set, rel_path, language)` (GRAPH-REAL-REPO Stage 1):** helper em `engine/graph/gradle_modules.py` que deriva a plataforma de cada arquivo (source-set KMP explícito, senão Swift/ObjC→ios, `.java`→android, Kotlin/XML sob `src/<sourceSet>/`→android).
```

- [ ] **Step 6: Commit**

```bash
git add engine/graph/gradle_modules.py tests/unit/test_infer_platform.py CHANGELOG.md
git commit -m "feat(graph): infer_platform deriva plataforma por source-set + layout"
```

---

## Task 4: Populate `platform` on the full-build and incremental insert paths

**Files:**
- Modify: `engine/graph/builder.py:534-543` (the `_ingest_file` INSERT)
- Modify: `engine/graph/incremental.py:355-364` (the `_refresh_file` INSERT)
- Modify: `CHANGELOG.md`
- Test: `tests/unit/test_platform_populated_build_and_incremental.py` (create)

**Interfaces:**
- Consumes: `infer_platform(...)` (Task 3); the `files.platform` column (Task 2).
- Produces: `files.platform` populated by both insert paths, kept in sync on re-ingest via the `ON CONFLICT(path) DO UPDATE SET ... platform=excluded.platform`.

- [ ] **Step 1: Write the population test (RED)**

Create `tests/unit/test_platform_populated_build_and_incremental.py`:

```python
"""Population of `files.platform` on full build + incremental re-ingest."""

from __future__ import annotations

from pathlib import Path

from engine.graph import incremental
from engine.graph.builder import build_full
from engine.utils.sqlite_io import open_db


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_tree(proj: Path) -> None:
    _write(proj / "settings.gradle.kts",
           'include(":shared")\ninclude(":app")\ninclude(":iosApp")\n')
    # Common (KMP source-set).
    _write(proj / "shared" / "src" / "commonMain" / "kotlin" / "Fmt.kt",
           "package x\nfun Long.fmt(): String = \"\"\n")
    # Android in standard /src/main/ layout (no KMP source-set).
    _write(proj / "app" / "src" / "main" / "kotlin" / "Home.kt",
           "package x\nclass Home\n")
    # iOS Swift under Xcode layout.
    _write(proj / "iosApp" / "Sources" / "HomeView.swift",
           "import SwiftUI\nstruct HomeView: View { var body: some View { Text(\"x\") } }\n")


def _platform_of(conn, suffix: str) -> str | None:
    row = conn.execute(
        "SELECT platform FROM files WHERE path LIKE ?", (f"%{suffix}",)
    ).fetchone()
    assert row is not None, f"no file row for {suffix}"
    return row["platform"]


def test_build_full_populates_platform(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    _build_tree(proj)
    db = proj / "graph.db"
    build_full(proj, db_path=db)
    conn = open_db(db, create=False)
    try:
        assert _platform_of(conn, "shared/src/commonMain/kotlin/Fmt.kt") == "common"
        assert _platform_of(conn, "app/src/main/kotlin/Home.kt") == "android"
        assert _platform_of(conn, "iosApp/Sources/HomeView.swift") == "ios"
    finally:
        conn.close()


def test_incremental_reingest_keeps_platform(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    _build_tree(proj)
    db = proj / "graph.db"
    build_full(proj, db_path=db)
    home = proj / "app" / "src" / "main" / "kotlin" / "Home.kt"
    home.write_text("package x\nclass Home { val v = 1 }\n", encoding="utf-8")
    incremental.update_file(proj, home, db_path=db)
    conn = open_db(db, create=False)
    try:
        assert _platform_of(conn, "app/src/main/kotlin/Home.kt") == "android"
    finally:
        conn.close()
```

- [ ] **Step 2: Run the test to verify it fails (RED)**

Run: `.venv/bin/pytest tests/unit/test_platform_populated_build_and_incremental.py -v`
Expected: FAIL — `platform` is `None` (column exists but no insert path writes it yet).

- [ ] **Step 3a: Populate in `_ingest_file` (builder)**

In `engine/graph/builder.py`, ensure `infer_platform` is imported. Edit the import block (lines 30-33):

```python
from engine.graph.gradle_modules import (
    infer_module_and_source_set,
    infer_platform,
    load_gradle_modules,
)
```

Then, in `_ingest_file`, right after `module, source_set = infer_module_and_source_set(...)` (line 521), compute platform, and update the INSERT (lines 534-543):

```python
    module, source_set = infer_module_and_source_set(rel, gradle_modules or {})
    platform = infer_platform(module, source_set, rel, language)

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
        "INSERT INTO files(path, language, module, source_set, platform, lines, last_modified, sha256) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET "
        "  language=excluded.language, module=excluded.module, "
        "  source_set=excluded.source_set, platform=excluded.platform, "
        "  lines=excluded.lines, last_modified=excluded.last_modified, "
        "  sha256=excluded.sha256",
        (rel, language, module, source_set, platform, line_count, last_modified, sha256),
    )
```

- [ ] **Step 3b: Populate in `_refresh_file` (incremental)**

`incremental.py` already imports `infer_module_and_source_set, load_gradle_modules` from `gradle_modules` (lines 37-40). Add `infer_platform`:

```python
from engine.graph.gradle_modules import (
    infer_module_and_source_set,
    infer_platform,
    load_gradle_modules,
)
```

Then in `_refresh_file`, after `module, source_set = infer_module_and_source_set(...)` (line 342), compute platform and update the INSERT (lines 355-364):

```python
    module, source_set = infer_module_and_source_set(rel, gradle_modules or {})
    platform = infer_platform(module, source_set, rel, language)

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
        "INSERT INTO files(path, language, module, source_set, platform, lines, last_modified, sha256) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET "
        "  language=excluded.language, module=excluded.module, "
        "  source_set=excluded.source_set, platform=excluded.platform, "
        "  lines=excluded.lines, last_modified=excluded.last_modified, "
        "  sha256=excluded.sha256",
        (rel, language, module, source_set, platform, line_count, last_modified, sha256),
    )
```

- [ ] **Step 4: Run the test to verify it passes (GREEN)**

Run: `.venv/bin/pytest tests/unit/test_platform_populated_build_and_incremental.py -v`
Expected: `2 passed`.

- [ ] **Step 5: Confirm the incremental lane still passes**

Run: `.venv/bin/pytest tests/unit/test_incremental_conn_lifecycle.py tests/unit/test_files_platform_column.py -q`
Expected: all pass.

- [ ] **Step 6: CHANGELOG entry**

`## [Unreleased] > ### Added`:

```markdown
- **`files.platform` populada no build full (`_ingest_file`) e incremental (`_refresh_file`)** via `infer_platform`; re-ingest mantém a plataforma consistente pelo `ON CONFLICT ... platform=excluded.platform` (GRAPH-REAL-REPO Stage 1).
```

- [ ] **Step 7: Commit**

```bash
git add engine/graph/builder.py engine/graph/incremental.py CHANGELOG.md tests/unit/test_platform_populated_build_and_incremental.py
git commit -m "feat(graph): popula files.platform no build full e incremental"
```

---

## Task 5: Platform-aware detection + read queries

**Files:**
- Modify: `engine/graph/duplicates.py:294-335` (`_q_redundant_platform_specific`)
- Modify: `engine/graph/duplicates.py:230-265` (`_q_kmp_migration_candidates`)
- Modify: `engine/graph/queries.py:619-658` (`find_redundant_platform_specific`)
- Modify: `engine/graph/queries.py:526-559` (`find_kmp_migration_candidates`)
- Modify: `CHANGELOG.md`
- Test: `tests/unit/test_platform_aware_reuse_queries.py` (create)

**Interfaces:**
- Consumes: `files.platform` column (Task 2), populated (Task 4) or hand-seeded in the test.
- Produces: `redundant-platform-specific` discriminates `common` (shared side) ↔ `android` (redundant side) by `files.platform`; `kmp-migration-candidate` gates the Kotlin side by `platform = 'common'`. Finding row shape (SELECT columns) is unchanged — only the WHERE clause changes.

**Semantic change (documented).** The old queries keyed off `module LIKE 'androidApp%'` + literal `source_set`. The new queries key off `files.platform`:
- `redundant-platform-specific`: shared side `shared_f.platform = 'common'`, redundant side `android_f.platform = 'android'`. This grows the redundant side to include Android code under `/src/main/` in modules NOT named `androidApp*` (today missed).
- `kmp-migration-candidate`: Kotlin side `kt_f.platform = 'common'` (replaces `module = 'shared'/'shared:%'` + `source_set = 'commonMain' OR source_set IS NULL`). The Swift side is unchanged (any `.swift func` matching receiver+name). The old `source_set IS NULL` fallback is subsumed by honest platform inference.

**Note on duplication:** `duplicates.py` (build-time detection, materializes `reuse_findings`) and `queries.py` (read-time for `forge graph`) carry near-identical SQL for each of these two queries. Edit BOTH; keep them character-identical in the changed clause. Extracting a shared SQL constant is out of scope for Stage 1 (Mandamento #4) — flag it as a follow-on, do not refactor here.

- [ ] **Step 1: Write the detection + read-query test (RED)**

Create `tests/unit/test_platform_aware_reuse_queries.py`. Scenario: a common↔android byte-identical Kotlin extension where the Android copy lives in `app/src/main/` (module `app`, `source_set` NULL, `platform` `android`) — today's heuristic misses it (`module` is not `androidApp%`, `source_set` is not `androidMain`); the platform-aware query must catch it.

```python
"""Platform-aware `redundant-platform-specific` + `kmp-migration-candidate`.

The Android redundant copy lives under `app/src/main/` (module `app`,
source_set NULL) — the pre-Stage-1 heuristic (`module LIKE 'androidApp%'` or
`source_set='androidMain'`) misses it. The platform-aware query catches it via
`files.platform='android'`.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.graph.duplicates import detect_all_reuse_findings
from engine.utils.sqlite_io import open_db, transaction


def _insert_file(conn, path, module, source_set, platform, language="kotlin") -> int:
    cur = conn.execute(
        "INSERT INTO files(path, language, module, source_set, platform) "
        "VALUES (?, ?, ?, ?, ?)",
        (path, language, module, source_set, platform),
    )
    return cur.lastrowid


def _insert_kt_ext(conn, file_id, *, name="formatTime", receiver="Long",
                   sig="formatTime(): String", body_hash="hZ", tokens='["a","b"]',
                   line=10) -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind, signature, line_start, "
        "receiver_type, body_hash, body_tokens, modifiers) "
        "VALUES (?, ?, 'fun', ?, ?, ?, ?, ?, '')",
        (file_id, name, sig, line, receiver, body_hash, tokens),
    )


def _insert_swift_func(conn, file_id, *, name="formatTime", receiver="Long",
                       sig="formatTime() -> String", tokens='["a","b"]', line=5) -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind, signature, line_start, "
        "receiver_type, body_hash, body_tokens, modifiers) "
        "VALUES (?, ?, 'func', ?, ?, ?, NULL, ?, '')",
        (file_id, name, sig, line, receiver, tokens),
    )


def test_read_query_redundant_catches_src_main_android(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            shared_f = _insert_file(
                conn, "shared/src/commonMain/kotlin/Time.kt",
                "shared", "commonMain", "common")
            android_f = _insert_file(
                conn, "app/src/main/kotlin/Time.kt",
                "app", None, "android")
            _insert_kt_ext(conn, shared_f)
            _insert_kt_ext(conn, android_f)
    finally:
        conn.close()
    rows = queries.find_redundant_platform_specific(tmp_path, db_path=db)
    assert len(rows) == 1
    assert rows[0]["name"] == "formatTime"
    assert rows[0]["shared_module"] == "shared"
    assert rows[0]["android_module"] == "app"


def test_detection_materializes_redundant_finding(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            shared_f = _insert_file(
                conn, "shared/src/commonMain/kotlin/Time.kt",
                "shared", "commonMain", "common")
            android_f = _insert_file(
                conn, "app/src/main/kotlin/Time.kt",
                "app", None, "android")
            _insert_kt_ext(conn, shared_f)
            _insert_kt_ext(conn, android_f)
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM reuse_findings "
            "WHERE category = 'redundant-platform-specific'"
        ).fetchone()["c"]
        assert n == 1
    finally:
        conn.close()


def test_kmp_migration_gated_by_common_platform(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            kt_f = _insert_file(
                conn, "shared/src/commonMain/kotlin/Time.kt",
                "shared", "commonMain", "common")
            sw_f = _insert_file(
                conn, "iosApp/Sources/Time.swift",
                "iosApp", None, "ios", language="swift")
            _insert_kt_ext(conn, kt_f)
            _insert_swift_func(conn, sw_f)
    finally:
        conn.close()
    rows = queries.find_kmp_migration_candidates(tmp_path, db_path=db)
    assert len(rows) == 1
    assert rows[0]["name"] == "formatTime"
    assert rows[0]["kotlin_module"] == "shared"
    assert rows[0]["swift_module"] == "iosApp"
```

- [ ] **Step 2: Run the test to verify it fails (RED)**

Run: `.venv/bin/pytest tests/unit/test_platform_aware_reuse_queries.py -v`
Expected: `test_read_query_redundant_catches_src_main_android` and `test_detection_materializes_redundant_finding` FAIL (return 0 rows — the `app` module fails `module LIKE 'androidApp%'` and `source_set` NULL fails `androidMain`). `test_kmp_migration_gated_by_common_platform` may currently PASS (the `shared`+`commonMain` file already satisfies the old filter) — it becomes a regression guard after the rewrite.

- [ ] **Step 3a: Rewrite `find_redundant_platform_specific` (queries.py)**

In `engine/graph/queries.py`, replace the WHERE-clause tail of the query (lines 649-655, the `AND (shared_f.module ...)` through `OR android_f.module LIKE 'androidApp%'\n              )` block) with platform predicates. The full new WHERE becomes:

```sql
            WHERE shared.kind = 'fun'
              AND shared.receiver_type IS NOT NULL
              AND shared.body_hash IS NOT NULL
              AND shared_f.path LIKE '%.kt'
              AND android_f.path LIKE '%.kt'
              AND shared_f.platform = 'common'
              AND android_f.platform = 'android'
            ORDER BY shared.receiver_type, shared.name
```

Also update the docstring (lines 610-616) to describe platform-based discrimination:

```python
    """Q16 — Android-side Kotlin extension identical to a common one.

    Discrimina por ``files.platform``: lado comum = ``platform='common'``;
    cópia redundante = ``platform='android'`` (inclui Android em ``/src/main/``
    em qualquer módulo, não só ``androidApp*``). O lado Android é redundante —
    consumidores devem usar a implementação comum.
    """
```

- [ ] **Step 3b: Rewrite `_q_redundant_platform_specific` (duplicates.py)**

In `engine/graph/duplicates.py`, apply the character-identical WHERE change to `_q_redundant_platform_specific` (lines 320-332). New WHERE:

```sql
        WHERE shared.kind = 'fun'
          AND shared.receiver_type IS NOT NULL
          AND shared.body_hash IS NOT NULL
          AND shared_f.path LIKE '%.kt'
          AND android_f.path LIKE '%.kt'
          AND shared_f.platform = 'common'
          AND android_f.platform = 'android'
        ORDER BY shared.receiver_type, shared.name
```

- [ ] **Step 3c: Rewrite `find_kmp_migration_candidates` (queries.py)**

In `engine/graph/queries.py`, replace the Kotlin-side filter of `find_kmp_migration_candidates` (lines 555-556):

```sql
              AND (kt_f.module = 'shared' OR kt_f.module LIKE 'shared:%')
              AND (kt_f.source_set = 'commonMain' OR kt_f.source_set IS NULL)
```

with:

```sql
              AND kt_f.platform = 'common'
```

Update the docstring (lines 518-523):

```python
    """Q14 — Swift extensions whose ``(receiver, name)`` mirrors Kotlin common.

    Returns raw matches (no token-similarity filter at SQL level — caller
    applies the Jaccard threshold). Kotlin side must be ``platform='common'``
    (commonMain, exposto via SKIE) para ser candidato a migração.
    """
```

- [ ] **Step 3d: Rewrite `_q_kmp_migration_candidates` (duplicates.py)**

In `engine/graph/duplicates.py`, apply the identical Kotlin-side filter change to `_q_kmp_migration_candidates` (lines 260-261):

```sql
          AND (kt_f.module = 'shared' OR kt_f.module LIKE 'shared:%')
          AND (kt_f.source_set = 'commonMain' OR kt_f.source_set IS NULL)
```

→

```sql
          AND kt_f.platform = 'common'
```

- [ ] **Step 4: Run the test to verify it passes (GREEN)**

Run: `.venv/bin/pytest tests/unit/test_platform_aware_reuse_queries.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Run the existing reuse-query lane (regression guard)**

Run: `.venv/bin/pytest tests/unit/test_query_q14_redundant_platform.py tests/unit/test_reuse_intelligence.py tests/unit/test_graph_queries.py -q`
Expected: pass. NOTE: the existing `tests/unit/test_query_q14_redundant_platform.py` hand-seeds files WITHOUT a `platform` value (it inserts `module`/`source_set` only), so its rows now have `platform=NULL` and the platform-aware query returns 0 → those assertions (`len(rows) == 1`) will FAIL. This is expected fallout of the semantic change. Update that test in THIS commit: add `platform="common"` to the shared file and `platform="android"` to the android file in both `_insert_file` calls so it exercises the new contract. (This is a same-change test-sync, not scope creep — the query it covers changed.) Re-run until green.

- [ ] **Step 6: CHANGELOG entry**

`## [Unreleased] > ### Changed`:

```markdown
- **Reuse-queries plataforma-específicas discriminam por `files.platform` (GRAPH-REAL-REPO Stage 1):** `redundant-platform-specific` (lado comum `platform='common'` ↔ redundante `platform='android'`) e `kmp-migration-candidate` (lado Kotlin `platform='common'`) substituem a heurística `module LIKE 'androidApp%'` + `source_set` literal. Universo de comparação cresce para incluir Android em `/src/main/` (qualquer módulo) e Swift do `iosApp`. Semântica dos findings preservada (só o WHERE mudou; row shape idêntico). Mudança espelhada em `duplicates.py` (detecção build-time) e `queries.py` (read-time). `test_query_q14_redundant_platform` atualizado para semear `platform`.
```

- [ ] **Step 7: Commit**

```bash
git add engine/graph/duplicates.py engine/graph/queries.py tests/unit/test_platform_aware_reuse_queries.py tests/unit/test_query_q14_redundant_platform.py CHANGELOG.md
git commit -m "feat(graph): reuse-queries discriminam plataforma via files.platform"
```

---

## Final validation gate (orchestrator-run — NOT a code task)

This is the AC-5 real-world check and the gate to Stage 2. The orchestrator (not a `gsd-executor` code task) runs it after all five tasks are green. It performs ZERO mutation to the app repo.

- [ ] **G1: Full-lane green + `forge verify`**

Run: `.venv/bin/pytest -q` (full lane, including `-m integration` and `-m e2e`)
Expected: all pass, no count regression vs. the branch baseline. Then `forge verify` → no hard fail.

- [ ] **G2: Re-spike against `inchurch-app-main` (isolated, read-only)**

Same protocol as the original spike: an isolated git worktree of feature-forge with its OWN `.venv` (editable-install trap — verify `python -c "import engine; print(engine.__file__)"` points INSIDE the worktree, not the main repo), graph DB written to the scratchpad (`/private/tmp/claude-503/.../scratchpad/inchurch-graph.db`), never inside the app. The app repo `/Users/thg.inchurch/StudioProjects/inchurch-app-main` is read-only input.

```bash
python - <<'PY'
from pathlib import Path
from engine.graph.builder import build_full
app = Path("/Users/thg.inchurch/StudioProjects/inchurch-app-main")
db = Path("/private/tmp/claude-503/.../scratchpad/inchurch-graph.db")
stats = build_full(app, db_path=db)
print("BUILD:", stats)  # (a) build completes + duration_ms
PY
```

Then report:
- **(a) Build completes + total time** (`duration_ms`; the import-resolution phase must finish in seconds, not >180s).
- **(b) `platform` distribution:** `SELECT platform, COUNT(*) FROM files GROUP BY platform` — the majority must be non-NULL (vs. ~415 non-NULL via `source_set` today).
- **(c) reuse-findings count per category:** `SELECT category, COUNT(*) FROM reuse_findings GROUP BY category` — especially `redundant-platform-specific` and `kmp-migration-candidate`.

These three numbers are the input for the Stage 2 go/no-go decision (broaden symbol universe / fuzzy similarity). Do NOT proceed to Stage 2 from within this plan.

---

## Self-Review — Spec coverage (AC → task)

| AC | Requirement | Task(s) |
|---|---|---|
| **AC-1** | `_resolve_import_targets` in ~O(imports+symbols); index-based; edge set preserved; verified by equivalence-on-fixture + scale | **Task 1** (rewrite + oracle equivalence test + scale smoke) |
| **AC-2** | `files.platform` column via idempotent ALTER (no SCHEMA_VERSION bump) + `infer_platform` rules; fixture per-branch classification | **Task 2** (column + DDL + migration) · **Task 3** (`infer_platform` table-driven) · **Task 4** (populated on build) |
| **AC-3** | `redundant-platform-specific` + `kmp-migration-candidate` discriminate via `files.platform`; semantics preserved; `/src/main/` android + `iosApp` swift now in universe; fixture that today produces no finding now does | **Task 5** (both queries in `duplicates.py` + `queries.py`; RED test = `/src/main/` android dup) |
| **AC-4** | Incremental honors `platform` (re-insert identical to full) | **Task 4** (`_refresh_file` INSERT) · **Task 2** (marker bump so incremental applies the ALTER on legacy DBs) |
| **AC-5** | Full-lane green + `forge verify` no hard fail + re-spike (build time, platform distribution, findings-per-category) | **Final validation gate** G1 + G2 |

**Placeholder scan:** none — every code step shows verbatim before/after against the real line anchors; every test step shows full test code; every run step gives the exact `.venv/bin/pytest …` command + expected output.

**Type/name consistency:** `_ensure_platform_column(conn)`, `infer_platform(module, source_set, rel_path, language)`, `_MIGRATIONS_KEY = "migrations_applied_v1_4"`, `idx_files_platform`, `files.platform`, and the `platform`-column INSERT signature are used identically across Tasks 2, 3, 4, and 5. `_resolve_import_targets(conn) -> None` keeps its signature (callers untouched). Doc-sync (`CHANGELOG.md` + `docs/schemas/graph.md`) is folded into each engine-touching commit per Mandamento #6 (no separate doc-only task).
