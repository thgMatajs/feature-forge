"""L2 — project-wide memory (.claude/memory/L2-project.yaml).

L2 captures cross-feature patterns, findings, frozen decisions, and naming
conventions that survive between features. Written by retrospective-agent
(via `forge evolve`), read by planning-conductor + sub-agents on every entry.

This module is a thin, typed shim over the YAML schema in
`docs/schemas/memory.md §L2`. It exposes a flat list of `L2Entry` objects
that aggregates the three buckets we care about most: patterns, findings,
and decisions-frozen. The on-disk file keeps each bucket separate so the
schema validator and human readers stay happy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from engine.memory import MemoryError
from engine.utils.iso import utc_now_iso
from engine.utils.paths import ensure_dir, memory_dir, memory_l2_path
from engine.utils.yaml_io import read_yaml_or_default, write_yaml

# ── Constants ────────────────────────────────────────────────────────────────

_VALID_KINDS = {
    "convention",
    "pattern",
    "anti-pattern",
    "domain-fact",
    "tooling",
    "risk",
    "finding",
    "decision-frozen",
    "naming-extra",
    "contradiction-resolved",
    "promotion-candidate",
}

# Map L2Entry.kind → on-disk bucket (matches docs/schemas/memory.md §L2).
_BUCKET_BY_KIND = {
    "pattern": "patterns",
    "anti-pattern": "patterns",
    "finding": "findings",
    "decision-frozen": "decisions-frozen",
    "convention": "patterns",
    "domain-fact": "patterns",
    "tooling": "patterns",
    "risk": "findings",
    "naming-extra": "naming-extras",
    "contradiction-resolved": "contradictions-resolved",
    "promotion-candidate": "promotion-candidates",
}


# ── Dataclass ────────────────────────────────────────────────────────────────


@dataclass
class L2Entry:
    """A single piece of L2 knowledge.

    Mirrors fields from the schema with light flattening so callers don't have
    to know which bucket (patterns/findings/decisions-frozen) they belong to.
    """

    id: str
    kind: str
    title: str
    body: str
    provenance: list[str] = field(default_factory=list)
    promoted_at: str = ""
    promoted_from: str = ""
    confidence: float = 1.0
    expires_at: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _empty_l2(project_root: Path) -> dict[str, Any]:
    return {
        "schema-version": 1,
        "project-slug": project_root.name,
        "last-updated": utc_now_iso(),
        "last-distillation": None,
        "patterns": [],
        "findings": [],
        "decisions-frozen": [],
        "naming-extras": [],
        "contradictions-resolved": [],
        "promotion-candidates": [],
    }


def _entry_from_pattern(p: dict[str, Any]) -> L2Entry:
    return L2Entry(
        id=str(p.get("id", "")),
        kind="pattern",
        title=str(p.get("name", "")),
        body=str(p.get("description", "")),
        provenance=list(p.get("detected-in", []) or []),
        promoted_at=str(p.get("promoted-at", "") or ""),
        promoted_from=str(p.get("promoted-from", "") or ""),
        confidence=float(p.get("confidence", 1.0)),
        expires_at=p.get("expires-at"),
        raw=p,
    )


def _entry_from_finding(f: dict[str, Any]) -> L2Entry:
    return L2Entry(
        id=str(f.get("id", "")),
        kind="finding",
        title=str(f.get("title", "")),
        body=str(f.get("description", "")),
        provenance=list(f.get("detected-in", []) or []),
        promoted_at=str(f.get("promoted-at", "") or ""),
        promoted_from=str(f.get("promoted-from", "") or ""),
        confidence=float(f.get("confidence", 1.0)),
        expires_at=f.get("expires-at"),
        raw=f,
    )


def _entry_from_naming_extra(n: dict[str, Any]) -> L2Entry:
    return L2Entry(
        id=str(n.get("id", "")),
        kind="naming-extra",
        title=str(n.get("context", "")),
        body=str(n.get("pattern", "")),
        provenance=list(n.get("examples", []) or []),
        promoted_at=str(n.get("promoted-at", "") or ""),
        promoted_from=str(n.get("promoted-from", "") or ""),
        confidence=float(n.get("confidence", 1.0)),
        expires_at=n.get("expires-at"),
        raw=n,
    )


def _entry_from_contradiction(c: dict[str, Any]) -> L2Entry:
    return L2Entry(
        id=str(c.get("id", "")),
        kind="contradiction-resolved",
        title=str(c.get("context", "")),
        body=str(c.get("resolution", "")),
        provenance=[str(c.get("feature", ""))] if c.get("feature") else [],
        promoted_at=str(c.get("timestamp", "") or ""),
        promoted_from=str(c.get("feature", "") or ""),
        confidence=1.0,
        expires_at=None,
        raw=c,
    )


def _entry_from_promotion_candidate(p: dict[str, Any]) -> L2Entry:
    appears = p.get("appears-in-features")
    confidence_raw = p.get("confidence", 0.0)
    return L2Entry(
        id=str(p.get("id") or p.get("proposed-name", "")),
        kind="promotion-candidate",
        title=str(p.get("proposed-name", "")),
        body=str(p.get("candidate-pattern", "")),
        provenance=[str(p.get("source", ""))] if p.get("source") else [],
        promoted_at=str(p.get("promoted-at", "") or ""),
        promoted_from=str(appears) if appears is not None else "",
        confidence=float(confidence_raw),
        expires_at=p.get("expires-at"),
        raw=p,
    )


def _entry_from_decision(d: dict[str, Any]) -> L2Entry:
    return L2Entry(
        id=str(d.get("id", "")),
        kind="decision-frozen",
        title=str(d.get("decision", "")),
        body=str(d.get("decision", "")),
        provenance=[str(d.get("by", ""))] if d.get("by") else [],
        promoted_at=str(d.get("locked-since", "") or ""),
        promoted_from=str(d.get("by", "") or ""),
        confidence=1.0,
        expires_at=None,
        raw=d,
    )


def _bucket_for(entry: L2Entry) -> str:
    return _BUCKET_BY_KIND.get(entry.kind, "patterns")


def _entry_to_payload(entry: L2Entry) -> dict[str, Any]:
    """Render an L2Entry back to its on-disk shape, preserving unknown keys."""
    if entry.kind == "naming-extra":
        payload: dict[str, Any] = dict(entry.raw) if entry.raw else {}
        payload.update(
            {
                "id": entry.id,
                "context": entry.title,
                "pattern": entry.body,
                "examples": list(entry.provenance),
            }
        )
        return payload

    if entry.kind == "contradiction-resolved":
        payload = dict(entry.raw) if entry.raw else {}
        payload.update(
            {
                "id": entry.id,
                "context": entry.title,
                "resolution": entry.body,
                "feature": entry.promoted_from or (
                    entry.provenance[0] if entry.provenance else ""
                ),
                "timestamp": entry.promoted_at or utc_now_iso(),
            }
        )
        return payload

    if entry.kind == "promotion-candidate":
        payload = dict(entry.raw) if entry.raw else {}
        payload.update(
            {
                "id": entry.id,
                "proposed-name": entry.title,
                "candidate-pattern": entry.body,
                "source": entry.provenance[0] if entry.provenance else "",
                "confidence": entry.confidence,
            }
        )
        if entry.promoted_from:
            try:
                payload["appears-in-features"] = int(entry.promoted_from)
            except ValueError:
                payload["appears-in-features"] = entry.promoted_from
        return payload

    if entry.kind == "decision-frozen":
        payload = dict(entry.raw) if entry.raw else {}
        payload.update(
            {
                "id": entry.id,
                "decision": entry.title or entry.body,
                "locked-since": entry.promoted_at or utc_now_iso(),
                "by": entry.promoted_from or "memory-distiller",
            }
        )
        return payload

    if entry.kind == "finding":
        payload = dict(entry.raw) if entry.raw else {}
        payload.update(
            {
                "id": entry.id,
                "title": entry.title,
                "description": entry.body,
                "detected-in": list(entry.provenance),
                "confidence": entry.confidence,
                "promoted-at": entry.promoted_at or utc_now_iso(),
                "promoted-from": entry.promoted_from,
            }
        )
        if entry.expires_at:
            payload["expires-at"] = entry.expires_at
        return payload

    # default: pattern (also covers convention/anti-pattern/domain-fact/tooling)
    payload = dict(entry.raw) if entry.raw else {}
    payload.update(
        {
            "id": entry.id,
            "name": entry.title,
            "description": entry.body,
            "detected-in": list(entry.provenance),
            "confidence": entry.confidence,
            "promoted-at": entry.promoted_at or utc_now_iso(),
            "promoted-from": entry.promoted_from,
        }
    )
    if entry.expires_at:
        payload["expires-at"] = entry.expires_at
    if entry.kind != "pattern":
        payload["kind"] = entry.kind
    return payload


# ── Read ─────────────────────────────────────────────────────────────────────


def _load_raw(project_root: Path) -> dict[str, Any]:
    path = memory_l2_path(project_root)
    data = read_yaml_or_default(path, _empty_l2(project_root))
    if not isinstance(data, dict):
        raise MemoryError(f"L2 file at {path} must be a YAML mapping")
    # Ensure required keys exist for tolerant reads on partially-populated files.
    for key in (
        "patterns",
        "findings",
        "decisions-frozen",
        "naming-extras",
        "contradictions-resolved",
        "promotion-candidates",
    ):
        data.setdefault(key, [])
    return data


def read_l2(project_root: Path) -> list[L2Entry]:
    """Read L2 and flatten patterns + findings + decisions-frozen to entries.

    Stable sort: by `id` lexicographically so callers can rely on order.
    """
    raw = _load_raw(project_root)
    entries: list[L2Entry] = []
    for p in raw.get("patterns") or []:
        if isinstance(p, dict):
            entries.append(_entry_from_pattern(p))
    for f in raw.get("findings") or []:
        if isinstance(f, dict):
            entries.append(_entry_from_finding(f))
    for d in raw.get("decisions-frozen") or []:
        if isinstance(d, dict):
            entries.append(_entry_from_decision(d))
    for n in raw.get("naming-extras") or []:
        if isinstance(n, dict):
            entries.append(_entry_from_naming_extra(n))
    for c in raw.get("contradictions-resolved") or []:
        if isinstance(c, dict):
            entries.append(_entry_from_contradiction(c))
    for p in raw.get("promotion-candidates") or []:
        if isinstance(p, dict):
            entries.append(_entry_from_promotion_candidate(p))
    entries.sort(key=lambda e: e.id)
    return entries


def find_entry(project_root: Path, entry_id: str) -> Optional[L2Entry]:
    """Return the entry with `id == entry_id`, or None."""
    for entry in read_l2(project_root):
        if entry.id == entry_id:
            return entry
    return None


def filter_entries(
    project_root: Path,
    *,
    kind: Optional[str] = None,
) -> list[L2Entry]:
    """Return entries filtered by kind. None → all entries."""
    if kind is not None and kind not in _VALID_KINDS:
        raise MemoryError(
            f"invalid kind '{kind}'; must be one of {sorted(_VALID_KINDS)}"
        )
    entries = read_l2(project_root)
    if kind is None:
        return entries
    return [e for e in entries if e.kind == kind]


# ── Write ────────────────────────────────────────────────────────────────────


def write_l2(
    project_root: Path,
    entries: list[L2Entry],
    *,
    backup: bool = True,
    replace_auxiliary: bool = False,
) -> None:
    """Replace L2 with a fresh document built from `entries`.

    Por default (`replace_auxiliary=False`), preserva os auxiliary buckets
    (naming-extras, contradictions-resolved, promotion-candidates) existentes
    no disco quando `entries` não traz nenhuma dessas kinds — assim callers
    que mexem só em patterns/findings/decisions não apagam histórico auxiliar.

    F11: passando `replace_auxiliary=True`, o caller pode explicitamente
    limpar auxiliary buckets — útil em distillation completa ou rewrite total.
    """
    seen: set[str] = set()
    for e in entries:
        if e.kind not in _VALID_KINDS:
            raise MemoryError(
                f"L2 entry {e.id!r} has invalid kind '{e.kind}'"
            )
        if not e.id:
            raise MemoryError("L2 entry id must be non-empty")
        if e.id in seen:
            raise MemoryError(f"duplicate L2 entry id: {e.id}")
        seen.add(e.id)
        if not 0.0 <= e.confidence <= 1.0:
            raise MemoryError(
                f"L2 entry {e.id} has confidence {e.confidence} outside [0,1]"
            )

    existing = _load_raw(project_root)

    buckets: dict[str, list[dict[str, Any]]] = {
        "patterns": [],
        "findings": [],
        "decisions-frozen": [],
        "naming-extras": [],
        "contradictions-resolved": [],
        "promotion-candidates": [],
    }
    for entry in entries:
        buckets[_bucket_for(entry)].append(_entry_to_payload(entry))

    doc: dict[str, Any] = dict(existing)
    doc["schema-version"] = 1
    doc.setdefault("project-slug", project_root.name)
    doc["last-updated"] = utc_now_iso()
    doc["patterns"] = buckets["patterns"]
    doc["findings"] = buckets["findings"]
    doc["decisions-frozen"] = buckets["decisions-frozen"]
    # F11: sobrescreve auxiliary buckets quando:
    # - caller forneceu entries para o bucket (preenche normalmente), OU
    # - `replace_auxiliary=True` (caller pede reset explícito, mesmo se vazio)
    # Caso contrário (default), preserva o conteúdo existente em disco.
    if buckets["naming-extras"] or replace_auxiliary:
        doc["naming-extras"] = buckets["naming-extras"]
    if buckets["contradictions-resolved"] or replace_auxiliary:
        doc["contradictions-resolved"] = buckets["contradictions-resolved"]
    if buckets["promotion-candidates"] or replace_auxiliary:
        doc["promotion-candidates"] = buckets["promotion-candidates"]

    ensure_dir(memory_dir(project_root))
    write_yaml(memory_l2_path(project_root), doc, atomic=True, backup=backup)


def remove_entry(project_root: Path, entry_id: str) -> None:
    """Remove an entry by id. No-op if absent."""
    current = read_l2(project_root)
    filtered = [e for e in current if e.id != entry_id]
    if len(filtered) == len(current):
        return
    write_l2(project_root, filtered, backup=True)


# ── Size / overflow ──────────────────────────────────────────────────────────


def l2_size_bytes(project_root: Path) -> int:
    """File size of L2-project.yaml in bytes. Returns 0 when file absent."""
    path = memory_l2_path(project_root)
    return path.stat().st_size if path.exists() else 0


def l2_overflow_check(project_root: Path, max_size_mb: float) -> bool:
    """True if L2 size exceeds `max_size_mb` (discipline §6 trigger)."""
    if max_size_mb <= 0:
        raise MemoryError("max_size_mb must be positive")
    return l2_size_bytes(project_root) > max_size_mb * 1024 * 1024


# ── Context-pack export ──────────────────────────────────────────────────────


def export_for_context_pack(project_root: Path) -> str:
    """Render L2 as a compact Markdown block suitable for sub-agent context packs.

    Empty buckets are omitted to keep tokens lean.
    """
    entries = read_l2(project_root)
    if not entries:
        return "## L2 project memory\n\n_no entries yet_\n"

    by_kind: dict[str, list[L2Entry]] = {}
    for e in entries:
        by_kind.setdefault(e.kind, []).append(e)

    lines: list[str] = ["## L2 project memory", ""]
    for kind in sorted(by_kind.keys()):
        lines.append(f"### {kind}")
        lines.append("")
        for e in by_kind[kind]:
            prov = ", ".join(e.provenance) if e.provenance else "—"
            lines.append(f"- **{e.id}** — {e.title}")
            if e.body:
                body = " ".join(e.body.split())
                lines.append(f"  - {body}")
            lines.append(f"  - provenance: {prov}; confidence: {e.confidence:.2f}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "L2Entry",
    "read_l2",
    "write_l2",
    "remove_entry",
    "find_entry",
    "filter_entries",
    "l2_size_bytes",
    "l2_overflow_check",
    "export_for_context_pack",
]
