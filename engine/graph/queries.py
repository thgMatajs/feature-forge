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


def find_reusable_helpers(
    project_root: Path,
    entity_types: list[str],
    *,
    util_path_fragments: Optional[list[str]] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q11 — existing helpers/extensions relevant to a feature's domain.

    Surfaces functions (including extensions) already present in `shared`
    whose signature references the given entity types OR live in a shared
    utility path. Used by planning-conductor Phase 4.5 to prefetch reuse
    candidates and write `existing-helpers.yaml` to L1 — the tech-spec-agent
    consumes the file deterministically without needing live graph access.

    Args:
        entity_types: domain entity names parsed from data-contract-spec.yaml
            (e.g., ["Bonsai", "Task", "Reminder"]). Empty list still matches
            general-purpose helpers in utility paths.
        util_path_fragments: substrings to consider "utility paths". Defaults
            to ["/util/", "/extensions/", "/core/"] when omitted.

    Returns:
        list of dicts with keys: name, signature, visibility, path, module,
        relevance ("signature-references-{Type}" or "utility-path").
        Ordered by (module, path, name) for stable output.
    """
    fragments = (
        util_path_fragments
        if util_path_fragments is not None
        else ["/util/", "/extensions/", "/core/"]
    )
    conn = _connect(project_root, db_path)
    try:
        sig_clauses = []
        params: list[str] = []
        for entity in entity_types:
            if not entity or not entity.strip():
                continue
            sig_clauses.append("s.signature LIKE ?")
            params.append(f"%{entity.strip()}%")

        path_clauses = []
        for frag in fragments:
            path_clauses.append("f.path LIKE ?")
            params.append(f"%{frag}%")

        where_or = sig_clauses + path_clauses
        if not where_or:
            return []
        where_combined = " OR ".join(where_or)

        rows = conn.execute(
            f"""
            SELECT DISTINCT s.name, s.signature, s.visibility,
                   f.path, f.module
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.kind = 'fun'
              AND s.visibility IN ('public', 'internal')
              AND (f.module = 'shared' OR f.module LIKE 'shared:%')
              AND ({where_combined})
            ORDER BY f.module, f.path, s.name
            """,
            params,
        ).fetchall()

        result: list[dict] = []
        for row in rows:
            signature = row["signature"] or ""
            relevance = "utility-path"
            for entity in entity_types:
                if entity and entity.strip() and entity in signature:
                    relevance = f"signature-references-{entity}"
                    break
            result.append(
                {
                    "name": row["name"],
                    "signature": signature,
                    "visibility": row["visibility"],
                    "path": row["path"],
                    "module": row["module"],
                    "relevance": relevance,
                }
            )
        return result
    finally:
        conn.close()


def find_duplicates_within_module(
    project_root: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q12 — same Kotlin extension declared 2+ times within ONE Gradle module.

    Groups by (module, source_set, receiver_type, name, signature, body_hash);
    only rows with COUNT > 1 are returned. Powers the
    ``consolidate-duplicate-helper`` evolution proposal.
    """
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
                   f.module AS module, f.source_set AS source_set,
                   GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path) AS occurrences,
                   COUNT(*) AS n
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.kind = 'fun'
              AND s.receiver_type IS NOT NULL
              AND s.body_hash IS NOT NULL
              AND f.path LIKE '%.kt'
            GROUP BY f.module, COALESCE(f.source_set, ''),
                     s.receiver_type, s.name, s.signature, s.body_hash
            HAVING COUNT(*) > 1
            ORDER BY n DESC, f.module, s.receiver_type, s.name
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def find_duplicates_cross_module(
    project_root: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q13 — same Kotlin extension declared in 2+ different Gradle modules.

    Groups by (receiver_type, name, signature, body_hash); only entries that
    span more than one module are returned. Powers
    ``promote-to-shared-helper``.
    """
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
                   GROUP_CONCAT(DISTINCT f.module) AS modules,
                   GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path) AS occurrences,
                   COUNT(DISTINCT f.module) AS n_modules,
                   COUNT(*) AS n_files
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.kind = 'fun'
              AND s.receiver_type IS NOT NULL
              AND s.body_hash IS NOT NULL
              AND f.path LIKE '%.kt'
            GROUP BY s.receiver_type, s.name, s.signature, s.body_hash
            HAVING COUNT(DISTINCT f.module) > 1
            ORDER BY n_modules DESC, n_files DESC, s.receiver_type, s.name
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def find_kmp_migration_candidates(
    project_root: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q14 — Swift extensions whose ``(receiver, name)`` mirrors Kotlin shared.

    Returns raw matches (no token-similarity filter at SQL level — caller
    applies the Jaccard threshold). Kotlin side must be in ``shared`` /
    ``shared:*`` AND ``commonMain`` source-set so SKIE can expose it.
    """
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT
              kt.name AS name,
              kt.receiver_type AS receiver,
              kt.signature AS kt_signature,
              kt.body_tokens AS kt_tokens,
              kt_f.module AS kotlin_module,
              kt_f.source_set AS kotlin_source_set,
              kt_f.id AS kotlin_file_id,
              kt_f.path AS kotlin_path,
              kt.line_start AS kotlin_line,
              sw.signature AS sw_signature,
              sw.body_tokens AS sw_tokens,
              sw_f.module AS swift_module,
              sw_f.id AS swift_file_id,
              sw_f.path AS swift_path,
              sw.line_start AS swift_line
            FROM symbols kt
            JOIN files kt_f ON kt.file_id = kt_f.id
            JOIN symbols sw
              ON sw.name = kt.name
             AND sw.receiver_type = kt.receiver_type
            JOIN files sw_f ON sw.file_id = sw_f.id
            WHERE kt.kind = 'fun'
              AND kt.receiver_type IS NOT NULL
              AND kt_f.path LIKE '%.kt'
              AND sw.kind = 'func'
              AND sw_f.path LIKE '%.swift'
              AND (kt_f.module = 'shared' OR kt_f.module LIKE 'shared:%')
              AND (kt_f.source_set = 'commonMain' OR kt_f.source_set IS NULL)
            ORDER BY kt.receiver_type, kt.name
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def find_near_duplicates(
    project_root: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q15 — same Kotlin extension signature but DIFFERENT body_hash values.

    Indicates accidental drift — e.g., ``Modifier.onFocusBlur(action)`` in two
    files where one is stateful and the other is a passthrough. Powers
    ``review-near-duplicate-helper`` (manual review required).
    """
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT s.name, s.receiver_type, s.signature, s.modifiers,
                   GROUP_CONCAT(DISTINCT s.body_hash) AS body_hashes,
                   GROUP_CONCAT(
                     f.id || ':' || s.line_start || ':' ||
                     COALESCE(s.body_hash, '_none_') || ':' || f.path
                   ) AS occurrences,
                   COUNT(DISTINCT s.body_hash) AS n_bodies,
                   COUNT(*) AS n_files
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.kind = 'fun'
              AND s.receiver_type IS NOT NULL
              AND s.body_hash IS NOT NULL
              AND f.path LIKE '%.kt'
            GROUP BY s.receiver_type, s.name, s.signature
            HAVING COUNT(DISTINCT s.body_hash) > 1
            ORDER BY n_bodies DESC, n_files DESC, s.receiver_type, s.name
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def find_redundant_platform_specific(
    project_root: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q16 — Android-side Kotlin extension identical to a ``shared:commonMain`` one.

    The Android copy is redundant — consumers should use the shared
    implementation. ``android_module`` covers two layouts:
      1. Multi-module Android: ``module LIKE 'androidApp%'``.
      2. KMP shared/androidMain: ``source_set = 'androidMain'``.
    """
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT shared.name AS name,
                   shared.receiver_type AS receiver,
                   shared.signature AS sig,
                   shared.body_hash AS body_hash,
                   shared.modifiers AS modifiers,
                   shared_f.module AS shared_module,
                   shared_f.id AS shared_file_id,
                   shared_f.path AS shared_path,
                   shared.line_start AS shared_line,
                   android_f.module AS android_module,
                   android_f.source_set AS android_source_set,
                   android_f.id AS android_file_id,
                   android_f.path AS android_path,
                   android.line_start AS android_line
            FROM symbols shared
            JOIN files shared_f ON shared.file_id = shared_f.id
            JOIN symbols android
              ON android.name = shared.name
             AND android.receiver_type = shared.receiver_type
             AND android.signature = shared.signature
             AND android.body_hash = shared.body_hash
             AND android.id != shared.id
            JOIN files android_f ON android.file_id = android_f.id
            WHERE shared.kind = 'fun'
              AND shared.receiver_type IS NOT NULL
              AND shared.body_hash IS NOT NULL
              AND shared_f.path LIKE '%.kt'
              AND android_f.path LIKE '%.kt'
              AND (shared_f.module = 'shared' OR shared_f.module LIKE 'shared:%')
              AND shared_f.source_set = 'commonMain'
              AND (
                ((android_f.module = 'shared' OR android_f.module LIKE 'shared:%')
                 AND android_f.source_set = 'androidMain')
                OR android_f.module LIKE 'androidApp%'
              )
            ORDER BY shared.receiver_type, shared.name
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def find_duplicate_ts_helpers(
    project_root: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Q17 — same TypeScript top-level helper duplicated 2+ times in one module."""
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT s.name, s.signature, s.body_hash, s.modifiers,
                   f.module AS module,
                   GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path) AS occurrences,
                   COUNT(*) AS n
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.kind = 'function'
              AND s.receiver_type IS NULL
              AND s.body_hash IS NOT NULL
              AND (f.path LIKE '%.ts' OR f.path LIKE '%.tsx'
                   OR f.path LIKE '%.js' OR f.path LIKE '%.jsx')
            GROUP BY f.module, s.name, s.signature, s.body_hash
            HAVING COUNT(*) > 1
            ORDER BY n DESC, f.module, s.name
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_reuse_findings(
    project_root: Path,
    *,
    category: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Read materialized ``reuse_findings`` (populated by detect post-passes).

    Combines per-finding metadata with locations into a single dict per
    finding. Filter by ``category`` to scope to one type (e.g.,
    ``duplicate-cross-module``).
    """
    conn = _connect(project_root, db_path)
    try:
        if category:
            findings = conn.execute(
                "SELECT * FROM reuse_findings WHERE category = ? ORDER BY confidence DESC, symbol_name",
                (category,),
            ).fetchall()
        else:
            findings = conn.execute(
                "SELECT * FROM reuse_findings ORDER BY confidence DESC, category, symbol_name"
            ).fetchall()

        result: list[dict] = []
        for f in findings:
            locations = conn.execute(
                """
                SELECT loc.module, loc.source_set, loc.line_start, loc.language,
                       loc.body_hash, files.path
                FROM reuse_finding_locations loc
                JOIN files ON files.id = loc.file_id
                WHERE loc.finding_id = ?
                ORDER BY loc.module, loc.line_start
                """,
                (f["id"],),
            ).fetchall()
            entry = dict(f)
            entry["locations"] = [dict(loc) for loc in locations]
            result.append(entry)
        return result
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
