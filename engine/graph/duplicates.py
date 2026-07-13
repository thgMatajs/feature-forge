"""Reuse-intelligence detection + proposal queuing.

Two halves:

1. **Detection post-passes** (called from ``builder.build_full`` and
   ``incremental.update_*``): run the six SQL queries Q12–Q17, compute
   per-category fingerprints, infer ``suggested_target`` via the module
   dependency closure, and materialize findings into ``reuse_findings`` /
   ``reuse_finding_locations``.

2. **Proposal queuing** (called from ``init.py`` Step 11.5 and
   ``reconfigure._handle_graph``): read materialized findings and enqueue
   ``DistillationProposal`` entries into ``proposed-evolutions.yaml`` —
   rejected fingerprints are filtered automatically by the distiller.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from engine.graph._body_text import jaccard_similarity, tokens_from_json
from engine.graph.gradle_deps import build_dependency_closure, infer_suggested_target
from engine.utils.paths import FEATURE_WORKFLOW_DIRNAME, graph_db_path
from engine.utils.sqlite_io import open_db

# Mapping from internal detection category to the proposal ``kind`` value
# accepted by ``engine/memory/distiller.py``. Keys MUST stay in sync with
# ``_VALID_KINDS`` in distiller.
CATEGORY_TO_PROPOSAL_KIND: dict[str, str] = {
    "duplicate-within-module": "consolidate-duplicate-helper",
    "duplicate-cross-module": "promote-to-shared-helper",
    "redundant-platform-specific": "remove-redundant-platform-helper",
    "near-duplicate": "review-near-duplicate-helper",
    "kmp-migration-candidate": "kmp-migration-candidate",
    "duplicate-ts-helper": "consolidate-ts-helper",
}

# Confidence baseline per category. ``kmp-migration-candidate`` overrides this
# at insertion time based on token-similarity score.
CATEGORY_CONFIDENCE: dict[str, float] = {
    "duplicate-within-module": 0.95,
    "duplicate-cross-module": 0.85,
    "redundant-platform-specific": 0.90,
    "near-duplicate": 0.40,
    "kmp-migration-candidate": 0.50,
    "duplicate-ts-helper": 0.95,
}

# Cross-language token-similarity gates — anything below 0.40 is dropped.
_KMP_SIMILARITY_FLOOR = 0.40
_KMP_SIMILARITY_TIERS: list[tuple[float, float]] = [
    (0.80, 0.75),
    (0.60, 0.60),
    (0.40, 0.50),
]


def detect_all_reuse_findings(
    conn: sqlite3.Connection,
    gradle_modules: dict[str, str],
    module_dep_rows: Iterable[tuple[str, str, str]],
) -> dict[str, int]:
    """Run the six detection passes and materialize results.

    Caller already holds the transaction. Existing ``reuse_findings`` /
    ``reuse_finding_locations`` rows are wiped by ``_reset_domain_tables`` in
    full rebuild, so we only INSERT here. For incremental, callers may
    pre-DELETE specific findings (left as future work).

    Priority dedup: Q16 (redundant-platform-specific) takes precedence over
    Q12 (within-module) and Q13 (cross-module) when the same (receiver, name,
    sig, body_hash) appears. Q15 (near-duplicate) is excluded for any
    (receiver, name, sig) that already produced a Q12/Q13 match.

    Returns counts per category.
    """
    closure = build_dependency_closure(module_dep_rows)

    # Track keys already claimed by higher-priority categories to enforce dedup.
    claimed_exact: set[tuple[str, str, str, str]] = set()        # (receiver, name, sig, body_hash)
    claimed_signature: set[tuple[str, str, str]] = set()         # (receiver, name, sig)

    counts: dict[str, int] = {}

    # Q16 — redundant-platform-specific (highest precedence)
    redundant_rows = _q_redundant_platform_specific(conn)
    counts["redundant-platform-specific"] = 0
    for row in redundant_rows:
        key = (
            row["receiver"] or "",
            row["name"],
            row["sig"] or "",
            row["body_hash"] or "",
        )
        if key in claimed_exact:
            continue
        claimed_exact.add(key)
        claimed_signature.add((row["receiver"] or "", row["name"], row["sig"] or ""))
        _persist_redundant_platform_finding(conn, row, gradle_modules, closure)
        counts["redundant-platform-specific"] += 1

    # Q12 — within-module
    within_rows = _q_duplicates_within_module(conn)
    counts["duplicate-within-module"] = 0
    for row in within_rows:
        key = (
            row["receiver_type"] or "",
            row["name"],
            row["signature"] or "",
            row["body_hash"] or "",
        )
        if key in claimed_exact:
            continue
        claimed_exact.add(key)
        claimed_signature.add(
            (row["receiver_type"] or "", row["name"], row["signature"] or "")
        )
        _persist_within_module_finding(conn, row, gradle_modules, closure)
        counts["duplicate-within-module"] += 1

    # Q13 — cross-module
    cross_rows = _q_duplicates_cross_module(conn)
    counts["duplicate-cross-module"] = 0
    for row in cross_rows:
        key = (
            row["receiver_type"] or "",
            row["name"],
            row["signature"] or "",
            row["body_hash"] or "",
        )
        if key in claimed_exact:
            continue
        claimed_exact.add(key)
        claimed_signature.add(
            (row["receiver_type"] or "", row["name"], row["signature"] or "")
        )
        _persist_cross_module_finding(conn, row, gradle_modules, closure)
        counts["duplicate-cross-module"] += 1

    # Q15 — near-duplicate (skip groups already in Q12/Q13/Q16)
    near_rows = _q_near_duplicates(conn)
    counts["near-duplicate"] = 0
    for row in near_rows:
        sig_key = (
            row["receiver_type"] or "",
            row["name"],
            row["signature"] or "",
        )
        if sig_key in claimed_signature:
            continue
        _persist_near_duplicate_finding(conn, row, gradle_modules, closure)
        counts["near-duplicate"] += 1

    # Q14 — kmp-migration-candidate (independent of Kotlin-side dedup)
    kmp_rows = _q_kmp_migration_candidates(conn)
    counts["kmp-migration-candidate"] = 0
    for row in kmp_rows:
        kt_tokens = tokens_from_json(row.get("kt_tokens"))
        sw_tokens = tokens_from_json(row.get("sw_tokens"))
        score = jaccard_similarity(kt_tokens, sw_tokens)
        if score < _KMP_SIMILARITY_FLOOR:
            continue
        confidence = _kmp_confidence_for_score(score)
        _persist_kmp_migration_finding(conn, row, gradle_modules, score, confidence)
        counts["kmp-migration-candidate"] += 1

    # Q17 — TypeScript duplicates (independent — no receiver overlap with Kotlin)
    ts_rows = _q_duplicate_ts_helpers(conn)
    counts["duplicate-ts-helper"] = 0
    for row in ts_rows:
        _persist_ts_duplicate_finding(conn, row, gradle_modules, closure)
        counts["duplicate-ts-helper"] += 1

    return counts


# ----- Direct SQL helpers (same shape as queries module but inside the
# active transaction; avoids opening a second connection mid-build).


def _q_duplicates_within_module(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
               f.module AS module, f.source_set AS source_set,
               GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
               COUNT(*) AS n
        FROM symbols s
        JOIN files f ON s.file_id = f.id
        WHERE s.kind IN ('fun', 'composable_fun')
          AND s.body_hash IS NOT NULL
          AND f.path LIKE '%.kt'
        GROUP BY f.module, COALESCE(f.source_set, ''),
                 COALESCE(s.receiver_type, ''), s.name, s.signature, s.body_hash
        HAVING COUNT(*) > 1
        ORDER BY n DESC, f.module, COALESCE(s.receiver_type, ''), s.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _q_duplicates_cross_module(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
               GROUP_CONCAT(DISTINCT f.module) AS modules,
               GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
               GROUP_CONCAT(COALESCE(f.source_set, '')) AS source_sets,
               COUNT(DISTINCT f.module) AS n_modules,
               COUNT(*) AS n_files
        FROM symbols s
        JOIN files f ON s.file_id = f.id
        WHERE s.kind IN ('fun', 'composable_fun')
          AND s.body_hash IS NOT NULL
          AND f.path LIKE '%.kt'
        GROUP BY COALESCE(s.receiver_type, ''), s.name, s.signature, s.body_hash
        HAVING COUNT(DISTINCT f.module) > 1
        ORDER BY n_modules DESC, n_files DESC, COALESCE(s.receiver_type, ''), s.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _q_kmp_migration_candidates(conn: sqlite3.Connection) -> list[dict]:
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
          AND kt_f.platform = 'common'
        ORDER BY kt.receiver_type, kt.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _q_near_duplicates(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.receiver_type, s.signature, s.modifiers,
               GROUP_CONCAT(DISTINCT s.body_hash) AS body_hashes,
               GROUP_CONCAT(
                 f.id || ':' || s.line_start || ':' ||
                 COALESCE(s.body_hash, '_none_') || ':' || f.path,
                 char(31)
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
    return [dict(r) for r in rows]


def _q_redundant_platform_specific(conn: sqlite3.Connection) -> list[dict]:
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
          AND shared_f.platform = 'common'
          AND android_f.platform = 'android'
        ORDER BY shared.receiver_type, shared.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _q_duplicate_ts_helpers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.signature, s.body_hash, s.modifiers,
               f.module AS module,
               GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
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
    return [dict(r) for r in rows]


# ----- Per-category persistence


def _persist_within_module_finding(
    conn: sqlite3.Connection,
    row: dict,
    gradle_modules: dict[str, str],
    closure: dict[str, frozenset[str]],
) -> None:
    occurrences = _parse_occurrences(row.get("occurrences"))
    if len(occurrences) < 2:
        return
    module = row.get("module") or ""
    source_set = row.get("source_set") or None
    fingerprint = _fingerprint(
        "duplicate-within-module",
        module,
        row.get("receiver_type") or "",
        row["name"],
        row.get("signature") or "",
        row.get("body_hash") or "",
    )
    suggested = infer_suggested_target(
        "duplicate-within-module", [module], closure, gradle_modules
    )
    finding_id = _insert_finding(
        conn,
        category="duplicate-within-module",
        group_id=fingerprint,
        symbol_name=row["name"],
        receiver_type=row.get("receiver_type"),
        canonical_signature=row.get("signature"),
        body_hash=row.get("body_hash"),
        primary_language="kotlin",
        modifiers=row.get("modifiers"),
        suggested_target=suggested,
        confidence=CATEGORY_CONFIDENCE["duplicate-within-module"],
        similarity_score=None,
    )
    if finding_id is None:
        return
    for occ in occurrences:
        _insert_location(
            conn,
            finding_id=finding_id,
            file_id=occ["file_id"],
            module=module,
            source_set=source_set,
            line_start=occ["line"],
            language="kotlin",
            body_hash=row.get("body_hash"),
        )


def _persist_cross_module_finding(
    conn: sqlite3.Connection,
    row: dict,
    gradle_modules: dict[str, str],
    closure: dict[str, frozenset[str]],
) -> None:
    occurrences = _parse_occurrences(row.get("occurrences"))
    if len(occurrences) < 2:
        return
    modules_csv = row.get("modules") or ""
    modules_in_group = sorted({m for m in modules_csv.split(",") if m})
    fingerprint = _fingerprint(
        "duplicate-cross-module",
        row.get("receiver_type") or "",
        row["name"],
        row.get("signature") or "",
        row.get("body_hash") or "",
    )
    suggested = infer_suggested_target(
        "duplicate-cross-module", modules_in_group, closure, gradle_modules
    )
    finding_id = _insert_finding(
        conn,
        category="duplicate-cross-module",
        group_id=fingerprint,
        symbol_name=row["name"],
        receiver_type=row.get("receiver_type"),
        canonical_signature=row.get("signature"),
        body_hash=row.get("body_hash"),
        primary_language="kotlin",
        modifiers=row.get("modifiers"),
        suggested_target=suggested,
        confidence=CATEGORY_CONFIDENCE["duplicate-cross-module"],
        similarity_score=None,
    )
    if finding_id is None:
        return
    for occ in occurrences:
        location_module = _lookup_module_for_file(conn, occ["file_id"])
        source_set = _lookup_source_set_for_file(conn, occ["file_id"])
        _insert_location(
            conn,
            finding_id=finding_id,
            file_id=occ["file_id"],
            module=location_module,
            source_set=source_set,
            line_start=occ["line"],
            language="kotlin",
            body_hash=row.get("body_hash"),
        )


def _persist_redundant_platform_finding(
    conn: sqlite3.Connection,
    row: dict,
    gradle_modules: dict[str, str],
    closure: dict[str, frozenset[str]],
) -> None:
    fingerprint = _fingerprint(
        "redundant-platform-specific",
        row.get("receiver") or "",
        row["name"],
        row.get("sig") or "",
        row.get("body_hash") or "",
        row.get("shared_module") or "",
        row.get("android_module") or "",
    )
    suggested = infer_suggested_target(
        "redundant-platform-specific",
        [row.get("shared_module") or "", row.get("android_module") or ""],
        closure,
        gradle_modules,
    )
    finding_id = _insert_finding(
        conn,
        category="redundant-platform-specific",
        group_id=fingerprint,
        symbol_name=row["name"],
        receiver_type=row.get("receiver"),
        canonical_signature=row.get("sig"),
        body_hash=row.get("body_hash"),
        primary_language="kotlin",
        modifiers=row.get("modifiers"),
        suggested_target=suggested,
        confidence=CATEGORY_CONFIDENCE["redundant-platform-specific"],
        similarity_score=None,
    )
    if finding_id is None:
        return
    _insert_location(
        conn,
        finding_id=finding_id,
        file_id=row["shared_file_id"],
        module=row.get("shared_module") or "",
        source_set="commonMain",
        line_start=row.get("shared_line") or 0,
        language="kotlin",
        body_hash=row.get("body_hash"),
    )
    _insert_location(
        conn,
        finding_id=finding_id,
        file_id=row["android_file_id"],
        module=row.get("android_module") or "",
        source_set=row.get("android_source_set"),
        line_start=row.get("android_line") or 0,
        language="kotlin",
        body_hash=row.get("body_hash"),
    )


def _persist_near_duplicate_finding(
    conn: sqlite3.Connection,
    row: dict,
    gradle_modules: dict[str, str],
    closure: dict[str, frozenset[str]],
) -> None:
    occurrences = _parse_near_duplicate_occurrences(row.get("occurrences"))
    if len(occurrences) < 2:
        return
    fingerprint = _fingerprint(
        "near-duplicate",
        row.get("receiver_type") or "",
        row["name"],
        row.get("signature") or "",
    )
    modules_in_group = sorted(
        {_lookup_module_for_file(conn, occ["file_id"]) for occ in occurrences}
    )
    suggested = infer_suggested_target(
        "near-duplicate", modules_in_group, closure, gradle_modules
    )
    finding_id = _insert_finding(
        conn,
        category="near-duplicate",
        group_id=fingerprint,
        symbol_name=row["name"],
        receiver_type=row.get("receiver_type"),
        canonical_signature=row.get("signature"),
        body_hash=None,
        primary_language="kotlin",
        modifiers=row.get("modifiers"),
        suggested_target=suggested,
        confidence=CATEGORY_CONFIDENCE["near-duplicate"],
        similarity_score=None,
    )
    if finding_id is None:
        return
    for occ in occurrences:
        _insert_location(
            conn,
            finding_id=finding_id,
            file_id=occ["file_id"],
            module=_lookup_module_for_file(conn, occ["file_id"]),
            source_set=_lookup_source_set_for_file(conn, occ["file_id"]),
            line_start=occ["line"],
            language="kotlin",
            body_hash=occ["body_hash"],
        )


def _persist_kmp_migration_finding(
    conn: sqlite3.Connection,
    row: dict,
    gradle_modules: dict[str, str],
    similarity_score: float,
    confidence: float,
) -> None:
    fingerprint = _fingerprint(
        "kmp-migration-candidate",
        row.get("receiver") or "",
        row["name"],
    )
    finding_id = _insert_finding(
        conn,
        category="kmp-migration-candidate",
        group_id=fingerprint,
        symbol_name=row["name"],
        receiver_type=row.get("receiver"),
        canonical_signature=row.get("kt_signature"),
        body_hash=None,
        primary_language="mixed",
        modifiers=None,
        suggested_target="replace Swift extension with SKIE call to shared Kotlin",
        confidence=confidence,
        similarity_score=similarity_score,
    )
    if finding_id is None:
        return
    _insert_location(
        conn,
        finding_id=finding_id,
        file_id=row["kotlin_file_id"],
        module=row.get("kotlin_module") or "",
        source_set=row.get("kotlin_source_set"),
        line_start=row.get("kotlin_line") or 0,
        language="kotlin",
        body_hash=None,
    )
    _insert_location(
        conn,
        finding_id=finding_id,
        file_id=row["swift_file_id"],
        module=row.get("swift_module") or "",
        source_set=None,
        line_start=row.get("swift_line") or 0,
        language="swift",
        body_hash=None,
    )


def _persist_ts_duplicate_finding(
    conn: sqlite3.Connection,
    row: dict,
    gradle_modules: dict[str, str],
    closure: dict[str, frozenset[str]],
) -> None:
    occurrences = _parse_occurrences(row.get("occurrences"))
    if len(occurrences) < 2:
        return
    module = row.get("module") or ""
    fingerprint = _fingerprint(
        "duplicate-ts-helper",
        module,
        row["name"],
        row.get("signature") or "",
        row.get("body_hash") or "",
    )
    suggested = infer_suggested_target(
        "duplicate-ts-helper", [module], closure, gradle_modules
    )
    finding_id = _insert_finding(
        conn,
        category="duplicate-ts-helper",
        group_id=fingerprint,
        symbol_name=row["name"],
        receiver_type=None,
        canonical_signature=row.get("signature"),
        body_hash=row.get("body_hash"),
        primary_language="typescript",
        modifiers=row.get("modifiers"),
        suggested_target=suggested,
        confidence=CATEGORY_CONFIDENCE["duplicate-ts-helper"],
        similarity_score=None,
    )
    if finding_id is None:
        return
    for occ in occurrences:
        _insert_location(
            conn,
            finding_id=finding_id,
            file_id=occ["file_id"],
            module=module,
            source_set=None,
            line_start=occ["line"],
            language="typescript",
            body_hash=row.get("body_hash"),
        )


# ----- Persistence helpers


def _insert_finding(
    conn: sqlite3.Connection,
    *,
    category: str,
    group_id: str,
    symbol_name: str,
    receiver_type: Optional[str],
    canonical_signature: Optional[str],
    body_hash: Optional[str],
    primary_language: str,
    modifiers: Optional[str],
    suggested_target: str,
    confidence: float,
    similarity_score: Optional[float],
) -> Optional[int]:
    """Upsert: existing fingerprint → return its id, refresh metadata.

    Locations are deleted-then-reinserted by the caller for each finding;
    that keeps the payload reflective of current state.
    """
    existing = conn.execute(
        "SELECT id FROM reuse_findings WHERE group_id = ?",
        (group_id,),
    ).fetchone()
    detected_at = datetime.now(timezone.utc).isoformat()
    if existing is not None:
        finding_id = existing["id"]
        conn.execute(
            """
            UPDATE reuse_findings SET
              category = ?,
              symbol_name = ?,
              receiver_type = ?,
              canonical_signature = ?,
              body_hash = ?,
              primary_language = ?,
              modifiers = ?,
              suggested_target = ?,
              confidence = ?,
              similarity_score = ?,
              detected_at = ?
            WHERE id = ?
            """,
            (
                category,
                symbol_name,
                receiver_type,
                canonical_signature,
                body_hash,
                primary_language,
                modifiers,
                suggested_target,
                confidence,
                similarity_score,
                detected_at,
                finding_id,
            ),
        )
        conn.execute(
            "DELETE FROM reuse_finding_locations WHERE finding_id = ?",
            (finding_id,),
        )
        return finding_id

    cursor = conn.execute(
        """
        INSERT INTO reuse_findings(
          category, group_id, symbol_name, receiver_type, canonical_signature,
          body_hash, primary_language, modifiers, suggested_target,
          confidence, similarity_score, detected_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            category,
            group_id,
            symbol_name,
            receiver_type,
            canonical_signature,
            body_hash,
            primary_language,
            modifiers,
            suggested_target,
            confidence,
            similarity_score,
            detected_at,
        ),
    )
    return cursor.lastrowid


def _insert_location(
    conn: sqlite3.Connection,
    *,
    finding_id: int,
    file_id: int,
    module: str,
    source_set: Optional[str],
    line_start: int,
    language: str,
    body_hash: Optional[str],
) -> None:
    conn.execute(
        """
        INSERT INTO reuse_finding_locations(
          finding_id, file_id, module, source_set, line_start, language, body_hash
        ) VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (finding_id, file_id, module, source_set, line_start, language, body_hash),
    )


# Unit Separator (ASCII 0x1F) — used as GROUP_CONCAT delimiter so that paths
# containing legal POSIX commas don't ambiguate the parse. See R2.2.
_OCC_SEP = "\x1f"


def _parse_occurrences(occ_csv: Optional[str]) -> list[dict]:
    """Parse the ``file_id:line:path`` triplets emitted by GROUP_CONCAT."""
    if not occ_csv:
        return []
    items: list[dict] = []
    for chunk in occ_csv.split(_OCC_SEP):
        parts = chunk.split(":", 2)
        if len(parts) < 2:
            continue
        try:
            file_id = int(parts[0])
            line = int(parts[1])
        except ValueError:
            continue
        path = parts[2] if len(parts) > 2 else ""
        items.append({"file_id": file_id, "line": line, "path": path})
    return items


def _parse_near_duplicate_occurrences(occ_csv: Optional[str]) -> list[dict]:
    """Near-duplicate Q15 stores ``file_id:line:body_hash:path``."""
    if not occ_csv:
        return []
    items: list[dict] = []
    for chunk in occ_csv.split(_OCC_SEP):
        parts = chunk.split(":", 3)
        if len(parts) < 3:
            continue
        try:
            file_id = int(parts[0])
            line = int(parts[1])
        except ValueError:
            continue
        body_hash = parts[2] if parts[2] != "_none_" else None
        path = parts[3] if len(parts) > 3 else ""
        items.append({"file_id": file_id, "line": line, "body_hash": body_hash, "path": path})
    return items


def _fingerprint(*parts: str) -> str:
    """Build a 64-char sha256 fingerprint for reuse-finding uniqueness.

    Format: ``sha256(parts joined by '\\x00')``. The NUL separator cannot
    appear in legal source text (paths, identifiers, signatures), so
    distinct partitions of the input stay distinct after the join — a
    plain ``|`` separator would collide on TypeScript union-type signatures
    like ``(x: string | number) => string`` (R2.1).

    Length matches the 64-char hex digest emitted by the distiller's
    canonical-form fingerprint, but the algorithms are not interchangeable:
    this fingerprint is used only for the duplicates table's UNIQUE index
    and the rejection-veto lookup against findings already marked rejected.
    """
    payload = "\x00".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _kmp_confidence_for_score(score: float) -> float:
    for threshold, confidence in _KMP_SIMILARITY_TIERS:
        if score >= threshold:
            return confidence
    return CATEGORY_CONFIDENCE["kmp-migration-candidate"]


def _lookup_module_for_file(conn: sqlite3.Connection, file_id: int) -> str:
    row = conn.execute("SELECT module FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        return ""
    return row["module"] or ""


def _lookup_source_set_for_file(conn: sqlite3.Connection, file_id: int) -> Optional[str]:
    row = conn.execute("SELECT source_set FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        return None
    return row["source_set"]


# ----- Proposal queuing (called by init.py + reconfigure.py)


def queue_proposals_from_table(project_root: Path) -> int:
    """Materialize reuse_findings → distillation proposals in proposed-evolutions.yaml.

    Returns the count of proposals queued (after rejection-fingerprint filter
    and de-dup against existing queue by fingerprint).
    """
    from engine.memory import MemoryError as DistillerMemoryError
    from engine.memory.distiller import (
        DistillationProposal,
        is_fingerprint_rejected,
        queue_proposal,
        read_proposals_queue,
    )

    conn = open_db(graph_db_path(project_root), create=False)
    try:
        findings = conn.execute(
            """
            SELECT id, category, group_id, symbol_name, receiver_type,
                   canonical_signature, body_hash, primary_language, modifiers,
                   suggested_target, confidence, similarity_score
            FROM reuse_findings
            ORDER BY confidence DESC, category, symbol_name
            """
        ).fetchall()
        if not findings:
            return 0

        existing_fingerprints = {
            p.fingerprint for p in read_proposals_queue(project_root) if p.fingerprint
        }

        proposals: list[DistillationProposal] = []
        counter = _next_proposal_counter(project_root)
        for f in findings:
            fingerprint = f["group_id"]
            if fingerprint in existing_fingerprints:
                continue
            if is_fingerprint_rejected(project_root, fingerprint):
                continue
            category = f["category"]
            kind = CATEGORY_TO_PROPOSAL_KIND.get(category)
            if kind is None:
                continue
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
            title = _build_proposal_title(f)
            description = _build_proposal_description(f, locations)
            # Distiller's wire format reads name/description from
            # proposed-change.payload — keep them populated so `forge evolve`
            # surfaces a non-empty title when listing proposals.
            payload = {
                "target-file": f"docs/{FEATURE_WORKFLOW_DIRNAME}/non-product/(generated)",
                "operation": "refactor-plan",
                "payload": {
                    "name": title,
                    "description": description,
                    "category": category,
                    "receiver_type": f["receiver_type"],
                    "symbol_name": f["symbol_name"],
                    "canonical_signature": f["canonical_signature"],
                    "body_hash": f["body_hash"],
                    "primary_language": f["primary_language"],
                    "modifiers": f["modifiers"],
                    "similarity_score": f["similarity_score"],
                    "locations": [dict(loc) for loc in locations],
                    "suggested_target": f["suggested_target"],
                    "suggested_subtype": "refactor",
                    "source_trigger": "init-scan",
                },
            }
            proposals.append(
                DistillationProposal(
                    id=f"P-{counter:04d}",
                    kind=kind,
                    title=title,
                    description=description,
                    provenance=["__init-scan__"],
                    confidence=f["confidence"] or 0.0,
                    fingerprint=fingerprint,
                    payload=payload,
                )
            )
            counter += 1
    finally:
        conn.close()

    queued = 0
    for proposal in proposals:
        try:
            queue_proposal(project_root, proposal)
            queued += 1
        except DistillerMemoryError:
            continue
    return queued


def _build_proposal_title(finding: sqlite3.Row) -> str:
    category = finding["category"]
    name = finding["symbol_name"]
    receiver = finding["receiver_type"] or "(top-level)"
    if category == "duplicate-within-module":
        return f"Consolidate duplicate helper `{receiver}.{name}` within module"
    if category == "duplicate-cross-module":
        return f"Promote duplicate helper `{receiver}.{name}` to shared ancestor"
    if category == "redundant-platform-specific":
        return f"Remove Android-side `{receiver}.{name}` — duplicate of shared"
    if category == "near-duplicate":
        return f"Review near-duplicate `{receiver}.{name}` (body drift)"
    if category == "kmp-migration-candidate":
        return f"Replace Swift `{receiver}.{name}` with shared Kotlin via SKIE"
    if category == "duplicate-ts-helper":
        return f"Consolidate duplicate TS helper `{name}` within module"
    return f"Reuse opportunity: `{receiver}.{name}`"


def _build_proposal_description(finding: sqlite3.Row, locations: list[sqlite3.Row]) -> str:
    category = finding["category"]
    n = len(locations)
    if category == "duplicate-within-module":
        return (
            f"Same `(receiver, name, signature, body_hash)` appears in {n} files within one "
            f"Gradle module. Extract to a shared `*Extension.kt` in the same module."
        )
    if category == "duplicate-cross-module":
        modules = sorted({loc["module"] for loc in locations})
        return (
            f"Identical implementation found in {n} files across {len(modules)} Gradle modules: "
            f"{', '.join(modules)}. Promote to the smallest common ancestor module."
        )
    if category == "redundant-platform-specific":
        return (
            "Android-side Kotlin extension is byte-for-byte identical to the shared `commonMain` "
            "version. The Android override is redundant — remove it and rely on shared."
        )
    if category == "near-duplicate":
        return (
            f"Same signature, different body across {n} files. Likely accidental drift — "
            f"decide which is canonical (or split into two intentionally different names)."
        )
    if category == "kmp-migration-candidate":
        sim = finding["similarity_score"]
        sim_str = f"{sim:.2f}" if sim is not None else "n/a"
        return (
            f"Swift extension and Kotlin shared helper share `(receiver, name)` with token "
            f"similarity {sim_str}. Replace the Swift implementation with a SKIE call into "
            f"shared so iOS uses the same logic."
        )
    if category == "duplicate-ts-helper":
        return (
            f"Same TypeScript helper duplicated in {n} files within one module. Extract to "
            f"`util/` and re-import."
        )
    return "Reuse opportunity detected during init-time scan."


def _next_proposal_counter(project_root: Path) -> int:
    """Pick a starting integer that won't collide with existing P-NNNN ids."""
    from engine.memory.distiller import read_proposals_queue as _read_queue

    existing = _read_queue(project_root)
    max_seen = 0
    for prop in existing:
        pid = getattr(prop, "id", "") or ""
        if isinstance(pid, str) and pid.startswith("P-"):
            tail = pid[2:]
            try:
                max_seen = max(max_seen, int(tail))
            except ValueError:
                continue
    return max_seen + 1
