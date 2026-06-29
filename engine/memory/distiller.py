"""Distillation driver — proposal queue + fingerprinting for `forge evolve`.

This module is the orchestrator-side counterpart to the `memory-distiller`
agent. It prepares the queue (`.claude/proposed-evolutions.yaml`), consults
the durable veto list (`.claude/rejected-evolutions.yaml`), and applies a
single accepted proposal to L2 — discipline §5 (single-by-single apply) and
§6 (overflow trigger).

The agent itself runs externally and produces `DistillationProposal` objects;
this module does not generate proposals on its own.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from engine.integrations.mem import mem_inbox_add
from engine.memory import MemoryError
from engine.memory.l2 import (
    l2_overflow_check,
    read_l2,
    write_l2,
)
from engine.utils.iso import utc_now_iso
from engine.utils.paths import claude_dir, ensure_dir
from engine.utils.sha256 import canonical_form_fingerprint
from engine.utils.yaml_io import read_yaml_or_default, write_yaml

# ── Constants ────────────────────────────────────────────────────────────────

_PROPOSED_FILE = "proposed-evolutions.yaml"
_REJECTED_FILE = "rejected-evolutions.yaml"
_PROPOSED_LOCK = ".proposed-evolutions.lock"
_REJECTED_LOCK = ".rejected-evolutions.lock"


@contextmanager
def _lockfile(lock_path: Path) -> Iterator[None]:
    """File lock advisory pra serializar mutações concorrentes em YAMLs de queue.

    POSIX: `fcntl.flock` (LOCK_EX). Windows: `msvcrt.locking`.
    Fallback no-op em plataformas sem suporte (mantém compat sem quebrar).
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+", encoding="utf-8")
    locked_posix = False
    try:
        if sys.platform == "win32":
            try:
                import msvcrt  # type: ignore[import-not-found]

                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            except (ImportError, OSError):
                pass
        else:
            try:
                import fcntl  # type: ignore[import-not-found]

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                locked_posix = True
            except ImportError:
                pass
        yield
    finally:
        try:
            if locked_posix:
                import fcntl  # type: ignore[import-not-found]

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        fh.close()

_VALID_KINDS = {
    "promote-to-l2",
    "consolidate-l2",
    "forget-l1",
    "distill-l2",
    "l1-to-l2-promotion",
    "template-patch",
    "agent-prompt-addition",
    "new-card-suggestion",
    "question-elimination",
    "convention-refinement",
    # Reuse-intelligence proposals (engine/graph/duplicates.py).
    "consolidate-duplicate-helper",
    "promote-to-shared-helper",
    "remove-redundant-platform-helper",
    "review-near-duplicate-helper",
    "kmp-migration-candidate",
    "consolidate-ts-helper",
}

# W-ROUTE 6b: os 3 kinds de L2-knowledge que agora vão pro mem inbox em vez
# de escrever L2. Compartilhado com engine/evolve.py (skip do overflow-guard).
_KNOWLEDGE_KINDS = frozenset({"promote-to-l2", "l1-to-l2-promotion", "consolidate-l2"})


# ── Dataclass ────────────────────────────────────────────────────────────────


@dataclass
class DistillationProposal:
    id: str
    kind: str
    title: str
    description: str
    provenance: list[str] = field(default_factory=list)
    confidence: float = 0.0
    fingerprint: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _proposed_path(project_root: Path) -> Path:
    return claude_dir(project_root) / _PROPOSED_FILE


def _rejected_path(project_root: Path) -> Path:
    return claude_dir(project_root) / _REJECTED_FILE


def _empty_proposed() -> dict[str, Any]:
    return {
        "schema-version": 1,
        "last-updated": utc_now_iso(),
        "last-source": "memory-distiller",
        "proposals": [],
    }


def _empty_rejected() -> dict[str, Any]:
    return {
        "schema-version": 1,
        "last-updated": utc_now_iso(),
        "rejections": [],
    }


def _validate_kind(kind: str) -> None:
    if kind not in _VALID_KINDS:
        raise MemoryError(
            f"invalid proposal kind '{kind}'; must be one of {sorted(_VALID_KINDS)}"
        )


def _proposal_to_payload(p: DistillationProposal) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": p.id,
        "type": p.kind,
        "confidence": p.confidence,
        "created-at": utc_now_iso(),
        "source": {
            "features": list(p.provenance),
            "trigger": "distillation",
        },
        "rationale": p.description,
        "proposed-change": p.payload
        or {
            "target-file": ".claude/memory/L2-project.yaml",
            "operation": "append",
            "payload": {
                "name": p.title,
                "description": p.description,
            },
        },
        "provenance": {
            "count": len(p.provenance),
            "feature-slugs": list(p.provenance),
        },
        "fingerprint": p.fingerprint or compute_proposal_fingerprint(
            {
                "type": p.kind,
                "name": p.title,
                "description": p.description,
                "provenance": {"feature-slugs": list(p.provenance)},
            }
        ),
    }
    return payload


def _proposal_from_payload(d: dict[str, Any]) -> DistillationProposal:
    provenance = d.get("provenance") or {}
    slugs = list(provenance.get("feature-slugs", []) or [])
    return DistillationProposal(
        id=str(d.get("id", "")),
        kind=str(d.get("type", "")),
        title=str(
            d.get("name")
            or d.get("proposed-change", {}).get("payload", {}).get("name", "")
            or d.get("title", "")
        ),
        description=str(d.get("rationale", "")),
        provenance=slugs,
        confidence=float(d.get("confidence", 0.0)),
        fingerprint=str(d.get("fingerprint", "")),
        payload=dict(d.get("proposed-change", {}) or {}),
    )


# ── Overflow ─────────────────────────────────────────────────────────────────


def detect_l2_overflow(project_root: Path, workflow_config: dict[str, Any]) -> bool:
    """Return True when L2 exceeds the configured size cap.

    Reads `workflow_config.memory.L2-project.max-size-mb`. Falls back to
    0.5 MB per docs/schemas/memory.md §L2 size management.
    """
    memory_cfg = workflow_config.get("memory") or {}
    l2_cfg = memory_cfg.get("L2-project") or {}
    max_mb = float(l2_cfg.get("max-size-mb", 0.5))
    return l2_overflow_check(project_root, max_mb)


# ── Queue ────────────────────────────────────────────────────────────────────


def _load_proposed(project_root: Path) -> dict[str, Any]:
    raw = read_yaml_or_default(_proposed_path(project_root), _empty_proposed())
    if not isinstance(raw, dict):
        raise MemoryError("proposed-evolutions.yaml must be a YAML mapping")
    raw.setdefault("schema-version", 1)
    raw.setdefault("proposals", [])
    return raw


def queue_proposal(project_root: Path, proposal: DistillationProposal) -> None:
    """Append a proposal to `.claude/proposed-evolutions.yaml`.

    Skips silently when the fingerprint is already in rejected-evolutions
    (discipline §5 — never re-propose a vetoed idea).
    """
    _validate_kind(proposal.kind)
    if not proposal.id:
        raise MemoryError("proposal id must be non-empty")

    if not proposal.fingerprint:
        proposal.fingerprint = compute_proposal_fingerprint(
            {
                "type": proposal.kind,
                "name": proposal.title,
                "description": proposal.description,
                "provenance": {"feature-slugs": list(proposal.provenance)},
            }
        )

    if is_fingerprint_rejected(project_root, proposal.fingerprint):
        return

    lock_path = claude_dir(project_root) / _PROPOSED_LOCK
    with _lockfile(lock_path):
        data = _load_proposed(project_root)
        proposals: list[dict[str, Any]] = list(data.get("proposals") or [])
        if any(p.get("id") == proposal.id for p in proposals):
            raise MemoryError(f"proposal id already queued: {proposal.id}")

        proposals.append(_proposal_to_payload(proposal))
        data["proposals"] = proposals
        data["last-updated"] = utc_now_iso()
        data["last-source"] = "memory-distiller"

        ensure_dir(_proposed_path(project_root).parent)
        write_yaml(_proposed_path(project_root), data, atomic=True, backup=True)


def read_proposals_queue(project_root: Path) -> list[DistillationProposal]:
    """Return queued proposals (ordered as in file)."""
    data = _load_proposed(project_root)
    return [
        _proposal_from_payload(p)
        for p in (data.get("proposals") or [])
        if isinstance(p, dict)
    ]


def remove_from_queue(project_root: Path, proposal_id: str) -> None:
    """Drain a single proposal by id. No-op when absent."""
    lock_path = claude_dir(project_root) / _PROPOSED_LOCK
    with _lockfile(lock_path):
        data = _load_proposed(project_root)
        proposals = [
            p for p in (data.get("proposals") or [])
            if isinstance(p, dict) and p.get("id") != proposal_id
        ]
        data["proposals"] = proposals
        data["last-updated"] = utc_now_iso()
        write_yaml(_proposed_path(project_root), data, atomic=True, backup=True)


# ── Rejected fingerprints ────────────────────────────────────────────────────


def _load_rejected(project_root: Path) -> dict[str, Any]:
    raw = read_yaml_or_default(_rejected_path(project_root), _empty_rejected())
    if not isinstance(raw, dict):
        raise MemoryError("rejected-evolutions.yaml must be a YAML mapping")
    raw.setdefault("schema-version", 1)
    raw.setdefault("rejections", [])
    return raw


def _next_rejection_id(rejections: list[dict[str, Any]]) -> str:
    max_n = 0
    for r in rejections:
        rid = str(r.get("id", ""))
        if rid.startswith("R-"):
            try:
                max_n = max(max_n, int(rid[2:]))
            except ValueError:
                continue
    return f"R-{max_n + 1:03d}"


def record_rejection(
    project_root: Path,
    fingerprint: str,
    *,
    rationale: str = "",
    proposal_snapshot: Optional[dict[str, Any]] = None,
    rejected_by: str = "user",
    # Back-compat with the previous (reason=, summary=) signature.
    reason: Optional[str] = None,
    summary: Optional[str] = None,
) -> None:
    """Persist a permanent rejection in `.claude/rejected-evolutions.yaml`.

    Canonical schema (docs/schemas/rejected-evolutions.md):

    ```yaml
    rejections:
      - id: R-NNN
        fingerprint: <sha256>
        rejected-at: <ISO>
        reason: <text>
        original-proposal-snapshot:
          id-at-rejection-time: P-NNN
          type: <enum>
          name: <slug>
          description: <text>
          provenance:
            count: N
            feature-slugs: [...]
          rationale: <text>
    ```

    `proposal_snapshot` is the full proposal dict at the moment of rejection.
    `rationale` is the human-readable reason captured from the user. The
    legacy `(reason=, summary=)` kwargs remain accepted for back-compat
    (mapped onto the new fields). No-op when fingerprint is already present.
    """
    if not fingerprint or len(fingerprint) != 64:
        raise MemoryError(
            "fingerprint must be a 64-char sha256 hex string"
        )

    lock_path = claude_dir(project_root) / _REJECTED_LOCK
    with _lockfile(lock_path):
        _record_rejection_locked(
            project_root,
            fingerprint,
            rationale=rationale,
            proposal_snapshot=proposal_snapshot,
            rejected_by=rejected_by,
            reason=reason,
            summary=summary,
        )


def _record_rejection_locked(
    project_root: Path,
    fingerprint: str,
    *,
    rationale: str,
    proposal_snapshot: Optional[dict[str, Any]],
    rejected_by: str,
    reason: Optional[str],
    summary: Optional[str],
) -> None:
    """Implementação interna de `record_rejection` — chamada já sob lock."""
    data = _load_rejected(project_root)
    rejections: list[dict[str, Any]] = list(data.get("rejections") or [])
    if any(r.get("fingerprint") == fingerprint for r in rejections):
        return

    final_reason = reason or "user permanent rejection"
    snap_in: dict[str, Any] = dict(proposal_snapshot or {})

    snapshot: dict[str, Any] = {
        "id-at-rejection-time": snap_in.get("id-at-rejection-time")
        or snap_in.get("id")
        or "",
        "type": snap_in.get("type") or snap_in.get("kind") or "",
        "name": snap_in.get("name") or snap_in.get("title") or "",
        "description": (
            snap_in.get("description")
            or snap_in.get("rationale")
            or (summary or "")
        ),
    }

    prov = snap_in.get("provenance")
    if isinstance(prov, dict):
        slugs = list(prov.get("feature-slugs") or [])
        snapshot["provenance"] = {
            "count": int(prov.get("count", len(slugs))),
            "feature-slugs": slugs,
        }
    elif isinstance(prov, list):
        snapshot["provenance"] = {
            "count": len(prov),
            "feature-slugs": list(prov),
        }
    else:
        snapshot["provenance"] = {"count": 0, "feature-slugs": []}

    if rationale:
        snapshot["rationale"] = rationale
    elif summary and "description" not in snap_in:
        snapshot.setdefault("rationale", summary)

    entry: dict[str, Any] = {
        "id": _next_rejection_id(rejections),
        "fingerprint": fingerprint,
        "rejected-at": utc_now_iso(),
        "rejected-by": rejected_by,
        "reason": final_reason,
        "original-proposal-snapshot": snapshot,
    }

    rejections.append(entry)
    data["rejections"] = rejections
    data["last-updated"] = utc_now_iso()

    ensure_dir(_rejected_path(project_root).parent)
    write_yaml(_rejected_path(project_root), data, atomic=True, backup=True)


def is_fingerprint_rejected(project_root: Path, fingerprint: str) -> bool:
    """True if the fingerprint is in `.claude/rejected-evolutions.yaml`."""
    if not fingerprint:
        return False
    data = _load_rejected(project_root)
    for r in data.get("rejections") or []:
        if isinstance(r, dict) and r.get("fingerprint") == fingerprint:
            return True
    return False


# ── Apply ────────────────────────────────────────────────────────────────────


def apply_proposal_to_l2(
    project_root: Path,
    proposal: DistillationProposal,
) -> str | None:
    """Apply a single proposal to L2 — discipline §5 (no batch).

    Behavior depends on `proposal.kind`:
    - `promote-to-l2` / `l1-to-l2-promotion` / `consolidate-l2` → enfileira no
      mem inbox como candidato curado (`mem inbox add --type reference`). O merge-
      semantic do consolidate-l2 é moot com L2 abandonado para conhecimento —
      vira candidato inbox como os outros dois (anti-envenenamento G11).
    - `forget-l1` → arquiva a feature L1 indicada por `proposal.payload.target`
      (ou primeiro elemento de `provenance`).
    - Demais kinds (`distill-l2`, `template-patch`, `agent-prompt-addition`,
      `new-card-suggestion`, `question-elimination`, `convention-refinement`):
      ainda não implementados em v1 — `NotImplementedError` para evitar
      silent no-op (a queue NÃO é drenada).

    Retorno (W-ROUTE 6d): o `mem-inbox-id` (de `result.data["id"]`) no branch de
    knowledge kinds; `None` em TODOS os outros branches (forget-l1, reuse-
    intelligence). O caller (`evolve`) grava esse id no evento `evolve-apply`
    pra o `forge undo` re-rotar pro `mem inbox reject`.
    """
    _validate_kind(proposal.kind)

    if is_fingerprint_rejected(project_root, proposal.fingerprint):
        raise MemoryError(
            f"refusing to apply proposal {proposal.id}: fingerprint is on the veto list"
        )

    if proposal.kind in _KNOWLEDGE_KINDS:
        # W-ROUTE 6b: knowledge proposals vão pro mem inbox (anti-envenenamento G11).
        # O merge-semantic do consolidate-l2 é moot com L2 abandonado para conhecimento
        # — vira candidato inbox como os outros dois.
        # round(confidence*4)+1 (não *5): evita banker's rounding de round(0.5*5)==2;
        # 0.0→1, 0.5→3, 0.8→4, 1.0→5. clamp [1,5] para confidence fora de [0,1].
        importance = max(1, min(5, round(proposal.confidence * 4) + 1))
        tags = ",".join(proposal.provenance) if proposal.provenance else None
        result = mem_inbox_add(
            project_root,
            title=proposal.title,
            body=proposal.description,
            mem_type="reference",
            importance=importance,
            tags=tags,
            source=f"forge-evolve:{proposal.id}",
            origin="manual",
        )
        if not result.ok:
            raise MemoryError(
                f"apply_proposal_to_l2: mem_inbox_add falhou para {proposal.id} — "
                f"{result.message} — queue não drenada (raise-não-drena)."
            )
        remove_from_queue(project_root, proposal.id)
        # W-ROUTE 6d: devolve o mem-inbox-id capturado (de `mem --json inbox add`)
        # pra o caller gravar no evento `evolve-apply` — o `forge undo` lê de volta.
        inbox_id = None
        if isinstance(result.data, dict):
            inbox_id = result.data.get("id")
        return inbox_id

    if proposal.kind == "forget-l1":
        _apply_forget_l1(project_root, proposal)
        remove_from_queue(project_root, proposal.id)
        return None

    if proposal.kind in {
        "consolidate-duplicate-helper",
        "promote-to-shared-helper",
        "remove-redundant-platform-helper",
        "review-near-duplicate-helper",
        "kmp-migration-candidate",
        "consolidate-ts-helper",
    }:
        # Reuse-intelligence proposals don't mutate L2 — they materialize a
        # feature-intake stub under non-product/ that the refactor flow picks
        # up via `forge plan refactor-...`.
        from engine.graph.reuse_apply import apply_reuse_intelligence_proposal

        apply_reuse_intelligence_proposal(project_root, proposal)
        remove_from_queue(project_root, proposal.id)
        return None

    # Demais kinds: explicitamente não implementados em v1.
    # NÃO drenar a queue — usuário precisa saber que NÃO foi aplicado.
    raise NotImplementedError(
        f"apply_proposal_to_l2: kind '{proposal.kind}' não implementado em v1 — FOLLOWUP v1.1"
    )


def _apply_forget_l1(
    project_root: Path,
    proposal: DistillationProposal,
) -> None:
    """Arquiva a feature L1 alvo. Target vem de `payload.target` ou provenance[0]."""
    target = (
        proposal.payload.get("target")
        if isinstance(proposal.payload, dict)
        else None
    )
    if not target and proposal.provenance:
        target = proposal.provenance[0]
    if not target:
        raise MemoryError(
            f"forget-l1 proposal {proposal.id} sem target — informar em payload.target"
        )

    summary = {
        "schema-version": 1,
        "feature-slug": str(target),
        "archived-at": utc_now_iso(),
        "archived-by": "memory-distiller",
        "rationale": proposal.description or "forget-l1 proposal accepted",
        "proposal-id": proposal.id,
    }

    from engine.memory.l1 import archive_feature as _archive_feature

    _archive_feature(str(target), project_root, summary)


# ── Fingerprint passthrough ──────────────────────────────────────────────────


def compute_proposal_fingerprint(proposal: dict[str, Any]) -> str:
    """Stable proposal fingerprint per discipline §4 — see utils/sha256.py.

    Accepts either the wire format (`provenance.feature-slugs`) or a flat
    `provenance: [...]` shape; normalises before hashing.
    """
    normalised = dict(proposal)
    prov = proposal.get("provenance")
    if isinstance(prov, list):
        normalised["provenance"] = {"feature-slugs": prov}
    return canonical_form_fingerprint(normalised)


# ── Convenience: build proposal from raw dict ────────────────────────────────


def proposal_from_dict(d: dict[str, Any]) -> DistillationProposal:
    """Build a DistillationProposal from a permissive dict (test/seed use)."""
    if not isinstance(d, dict):
        raise MemoryError("proposal payload must be a dict")
    provenance = d.get("provenance")
    if isinstance(provenance, dict):
        slugs = list(provenance.get("feature-slugs") or [])
    elif isinstance(provenance, list):
        slugs = list(provenance)
    else:
        slugs = []
    return DistillationProposal(
        id=str(d.get("id", "")),
        kind=str(d.get("kind") or d.get("type") or ""),
        title=str(d.get("title") or d.get("name") or ""),
        description=str(d.get("description") or d.get("rationale") or ""),
        provenance=slugs,
        confidence=float(d.get("confidence", 0.0)),
        fingerprint=str(d.get("fingerprint", "")),
        payload=dict(d.get("payload") or d.get("proposed-change") or {}),
    )


__all__ = [
    "DistillationProposal",
    "detect_l2_overflow",
    "queue_proposal",
    "read_proposals_queue",
    "remove_from_queue",
    "record_rejection",
    "is_fingerprint_rejected",
    "apply_proposal_to_l2",
    "compute_proposal_fingerprint",
    "proposal_from_dict",
]

# Optional dep tag (FOLLOWUP: portable filelock for Windows).
_ = Optional
