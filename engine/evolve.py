"""`forge evolve` — review-and-apply queued self-evolution proposals.

Single-by-single only (discipline §5 — never batch). For every queued
proposal that survives the fingerprint veto check, the user picks one of
four actions: aplicar / rejeitar / depois / ver-detalhe. L2 overflow
(discipline §6) is a pause: queue state is checkpointed and the user is
shown the three-paths menu.

Ctrl+C anywhere drops a deferred checkpoint and exits 130 (decision 27 /
discipline §7). Re-running `forge evolve` resumes automatically.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from engine.memory.distiller import (
    DistillationProposal,
    apply_proposal_to_l2,
    compute_proposal_fingerprint,
    detect_l2_overflow,
    is_fingerprint_rejected,
    read_proposals_queue,
    record_rejection,
    remove_from_queue,
)
from engine.memory.l1 import append_history
from engine.memory.l2 import l2_size_bytes
from engine.ui import question, renderer
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    claude_dir,
    ensure_dir,
    find_project_root,
    workflow_config_path,
)
from engine.utils.yaml_io import read_yaml_or_default, write_yaml
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    load_yaml_checkpoint as _load_yaml_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso as _utc_now_iso_shared

_CHECKPOINT_FILE = ".evolve-checkpoint.yaml"
_HISTORY_SLUG = "_evolve"


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp — thin shim sobre ``engine.utils.iso``."""
    return _utc_now_iso_shared()


def _checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / _CHECKPOINT_FILE


# Os 3 helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` —
# consolidação dos 30 duplicates apontada pelo finding #5 do master review
# do PR #11. ``evolve.py`` tem um shape de checkpoint distinto dos outros
# 9 handlers (sem ``_<Module>Checkpoint`` dataclass; ``_write_checkpoint``
# recebe argumentos posicionais e monta o payload localmente). Os nomes
# ``_write_checkpoint`` / ``_read_checkpoint`` / ``_clear_checkpoint``
# permanecem como API privada do módulo para preservar os contracts dos
# testes em ``tests/unit/test_engine_evolve_resume.py``.


def _write_checkpoint(
    project_root: Path,
    *,
    status: str,
    remaining_ids: list[str],
    note: str = "",
    intent_id: Optional[str] = None,
) -> None:
    """Write the evolve checkpoint atomically.

    DRIFT-1 W2.T3b — outcome C "extend": preservamos o payload legacy
    (status, saved-at, remaining-proposal-ids, note) e adicionamos o
    campo ``intent-id``. Default ``None`` quando o pause nao vem do
    chokepoint de prompts (L2 overflow, por ex.); quando vem, o campo
    correlaciona com ``.claude/state/forge-response.json`` na re-invocacao.
    """
    _save_yaml_checkpoint_io(
        _checkpoint_path(project_root),
        {
            "schema-version": 1,
            "status": status,
            "saved-at": _utc_now_iso(),
            "remaining-proposal-ids": remaining_ids,
            "note": note,
            "intent-id": intent_id,
        },
    )


def _read_checkpoint(project_root: Path) -> Optional[dict[str, Any]]:
    """Read the evolve checkpoint, returning ``None`` when absent."""
    return _load_yaml_checkpoint_io(_checkpoint_path(project_root))


def _clear_checkpoint(project_root: Path) -> None:
    """Remove the checkpoint — best-effort; silent on OSError (idempotent)."""
    _clear_checkpoint_io(_checkpoint_path(project_root))


def _load_workflow_config(project_root: Path) -> dict[str, Any]:
    cfg = read_yaml_or_default(workflow_config_path(project_root), {})
    return cfg if isinstance(cfg, dict) else {}


def _l2_max_mb(cfg: dict[str, Any]) -> float:
    """Lê `memory.l2.max-size-mb` (canônico) com fallback p/ `memory.L2-project.max-size-mb` (legacy).

    TODO v1.1: remover fallback após migrator-1-to-2 rodar contra configs antigos.
    """
    memory_cfg = cfg.get("memory") or {}
    l2_cfg = memory_cfg.get("l2") or memory_cfg.get("L2-project") or {}
    try:
        return float(l2_cfg.get("max-size-mb", 0.5))
    except (TypeError, ValueError):
        return 0.5


def _format_kb(size_bytes: int) -> str:
    return f"{size_bytes / 1024:.0f} KB"


def _render_queue_overview(proposals: list[DistillationProposal]) -> None:
    renderer.write("")
    renderer.write(
        renderer.bold(f"Propostas pendentes ({len(proposals)})")
    )
    renderer.write("")
    for i, p in enumerate(proposals, start=1):
        conf = f"{p.confidence:.2f}"
        prov = len(p.provenance)
        title = p.title or "(sem título)"
        if len(title) > 48:
            title = title[:45] + "…"
        line = (
            f"  [{i:>2}/{len(proposals)}] "
            f"{p.id:<7} {p.kind:<24} conf={conf}  trig={prov}  {title}"
        )
        renderer.write(line)
    renderer.write("")


def _render_proposal_detail(
    p: DistillationProposal,
    *,
    index: int,
    total: int,
    full: bool = False,
) -> None:
    renderer.write("")
    renderer.write(
        renderer.section_header(
            f"[{index}/{total}] {p.id} — {p.kind}",
            width=78,
        )
    )
    renderer.write("")
    renderer.write(f"  título      : {p.title or '—'}")
    renderer.write(f"  confidence  : {p.confidence:.2f}")
    renderer.write(
        f"  provenance  : {len(p.provenance)} feature(s) — "
        f"{', '.join(p.provenance) if p.provenance else '—'}"
    )
    if not full:
        body_one_line = " ".join((p.description or "").split())
        if len(body_one_line) > 200:
            body_one_line = body_one_line[:197] + "…"
        renderer.write(f"  rationale   : {body_one_line or '—'}")
    else:
        renderer.write("  rationale   :")
        for line in (p.description or "—").splitlines() or ["—"]:
            renderer.write(f"      {line}")
        if p.payload:
            renderer.write("  proposed-change:")
            for k, v in p.payload.items():
                if isinstance(v, (dict, list)):
                    renderer.write(f"      {k}: <{type(v).__name__}>")
                else:
                    renderer.write(f"      {k}: {v}")
    renderer.write("")


def _diff_preview(p: DistillationProposal) -> None:
    target = (p.payload or {}).get("target-file") or ".claude/memory/L2-project.yaml"
    operation = (p.payload or {}).get("operation") or "append"
    renderer.write(f"  📄 alvo: {target}  ({operation})")
    payload = (p.payload or {}).get("payload")
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(v, (dict, list)):
                renderer.write(f"     + {k}: <{type(v).__name__}>")
            else:
                renderer.write(f"     + {k}: {v}")
    renderer.write("")


_ACTION_OPTIONS = {
    "a": "aplicar",
    "r": "rejeitar (permanente)",
    "d": "depois (manter na fila)",
    "v": "ver detalhe completo",
}


def _action_intent_id(proposal_id: str) -> str:
    """Pre-compute the deterministic intent-id for the action ask on a proposal.

    DRIFT-1 W2.T3b — outcome C: exposed as helper so the run loop can
    persist intent-id no checkpoint ANTES de invocar question.ask
    (mantem o invariante de §3 — pending intent aponta pra state ja
    em disco). Question text espelha exatamente o usado em
    ``_action_for`` — qualquer drift entre as duas strings quebra o
    matching com forge-response.json.
    """
    return question.stable_intent_id(
        "ask",
        f"O que fazer com {proposal_id}?",
        _ACTION_OPTIONS,
        extra={"default": "d", "min-selected": None, "validator-hint": None},
    )


def _action_for(p: DistillationProposal) -> str:
    return question.ask(
        f"O que fazer com {p.id}?",
        _ACTION_OPTIONS,
        default="d",
        allow_pause=True,
    )


def _reject_proposal(project_root: Path, p: DistillationProposal) -> None:
    fp = p.fingerprint or compute_proposal_fingerprint(
        {
            "type": p.kind,
            "name": p.title,
            "description": p.description,
            "provenance": {"feature-slugs": list(p.provenance)},
        }
    )
    record_rejection(
        project_root,
        fp,
        rationale=p.description or f"{p.kind}: {p.title}",
        proposal_snapshot={
            "id-at-rejection-time": p.id,
            "type": p.kind,
            "name": p.title,
            "description": p.description,
            "provenance": {
                "count": len(p.provenance),
                "feature-slugs": list(p.provenance),
            },
        },
        rejected_by="user",
        reason="user permanent rejection",
    )
    remove_from_queue(project_root, p.id)


def _apply_proposal(
    project_root: Path,
    p: DistillationProposal,
    cfg: dict[str, Any],
) -> bool:
    """Apply with overflow guard. Returns True on success, False on overflow pause."""
    max_mb = _l2_max_mb(cfg)
    if detect_l2_overflow(project_root, cfg):
        renderer.write(
            renderer.colored(
                f"  🛑 L2 cheia — {_format_kb(l2_size_bytes(project_root))} "
                f"/ {max_mb * 1024:.0f} KB",
                "yellow",
            )
        )
        return False

    apply_proposal_to_l2(project_root, p)
    renderer.write(renderer.colored(f"  ✓ Aplicado {p.id}.", "green"))
    return True


def _three_paths_overflow(project_root: Path) -> str:
    renderer.write("")
    renderer.write(renderer.bold("🛑 L2 cheia"))
    renderer.write(
        "  Auto-distill **não roda aqui** — você está aprovando "
        "propostas e mudar L2 sob seus pés invalidaria as próximas."
    )
    renderer.write("")
    return question.ask(
        "Caminho?",
        {
            "a": "forge memory → distill L2 (depois retomo)",
            "b": "pausar e revisar depois (estado salvo)",
            "c": "abortar a sessão de evolve",
        },
        default="b",
        allow_pause=False,
    )


def _record_history_event(
    project_root: Path,
    kind: str,
    proposal_id: str,
    extras: Optional[dict[str, Any]] = None,
) -> None:
    """Log evolve activity under L1/_evolve/ — synthetic slug, audit only."""
    event: dict[str, Any] = {
        "kind": kind,
        "proposal-id": proposal_id,
        "command": "evolve",
    }
    if extras:
        event.update(extras)
    try:
        append_history(_HISTORY_SLUG, project_root, event)
    except Exception:
        pass


def _filter_rejected(
    project_root: Path,
    proposals: list[DistillationProposal],
) -> tuple[list[DistillationProposal], int]:
    kept: list[DistillationProposal] = []
    skipped = 0
    for p in proposals:
        fp = p.fingerprint or compute_proposal_fingerprint(
            {
                "type": p.kind,
                "name": p.title,
                "description": p.description,
                "provenance": {"feature-slugs": list(p.provenance)},
            }
        )
        if is_fingerprint_rejected(project_root, fp):
            skipped += 1
            continue
        kept.append(p)
    return kept, skipped


def run(argv: list[str]) -> int:
    """Entry point. Detects `.evolve-checkpoint.yaml` for resume support."""
    _ = argv

    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge evolve: {exc}\n")
        return 2

    cfg = _load_workflow_config(project_root)

    # ── Resume check ────────────────────────────────────────────────────────
    checkpoint = _read_checkpoint(project_root)
    if checkpoint:
        status = checkpoint.get("status", "?")
        renderer.write(
            renderer.dim(
                f"  retomando evolve (checkpoint: status={status}, "
                f"saved-at={checkpoint.get('saved-at', '?')})"
            )
        )

    # ── Load queue ──────────────────────────────────────────────────────────
    try:
        all_proposals = read_proposals_queue(project_root)
    except Exception as exc:
        sys.stderr.write(f"forge evolve: falha ao ler fila — {exc}\n")
        return 1

    # Se temos checkpoint com `remaining-proposal-ids`, filtra a queue
    # preservando a ORDEM original do checkpoint (não a ordem do read).
    # Garante que o usuário retome exatamente onde pausou.
    if checkpoint:
        remaining_ids = checkpoint.get("remaining-proposal-ids") or []
        if isinstance(remaining_ids, list) and remaining_ids:
            by_id = {p.id: p for p in all_proposals}
            ordered = [by_id[pid] for pid in remaining_ids if pid in by_id]
            if ordered:
                all_proposals = ordered
                renderer.write(
                    renderer.dim(
                        f"  filtrando para {len(ordered)} proposta(s) "
                        "remanescente(s) do checkpoint"
                    )
                )

    proposals, skipped = _filter_rejected(project_root, all_proposals)

    if not proposals:
        if skipped:
            renderer.write(
                renderer.dim(f"  {skipped} proposta(s) pulada(s) por veto.")
            )
        renderer.write("Nenhuma proposta pendente.")
        _clear_checkpoint(project_root)
        return 0

    # ── Pre-flight overflow ─────────────────────────────────────────────────
    if detect_l2_overflow(project_root, cfg):
        choice = _three_paths_overflow(project_root)
        _write_checkpoint(
            project_root,
            status="deferred-l2-full",
            remaining_ids=[p.id for p in proposals],
            note="overflow detected at start",
        )
        if choice == "a":
            renderer.write(
                "  Rode `forge memory` → distill L2, depois `forge evolve` "
                "novamente — o checkpoint resume daqui."
            )
        elif choice == "b":
            renderer.write("  Pausei. Checkpoint salvo.")
        else:
            renderer.write("  Abortado pelo usuário.")
        return 0

    # ── Overview ────────────────────────────────────────────────────────────
    renderer.write(renderer.bold("forge evolve"))
    renderer.write(
        "Vou abrir uma por uma. Cada decisão é sua — sem aplicar em lote."
    )
    _render_queue_overview(proposals)

    if skipped:
        renderer.write(
            renderer.dim(f"  ({skipped} proposta(s) ignorada(s) por veto fingerprint)")
        )

    # ── Single-by-single loop ───────────────────────────────────────────────
    total = len(proposals)
    cursor = 0
    while cursor < total:
        p = proposals[cursor]
        index = cursor + 1
        _render_proposal_detail(p, index=index, total=total, full=False)
        _diff_preview(p)

        # DRIFT-1 W2.T3b — persist checkpoint with the deterministic
        # intent-id for ``_action_for(p)`` BEFORE invoking the chokepoint.
        # If question.ask raises PausedForInputError, the host can pick
        # the response that matches this intent-id on re-invocation.
        _write_checkpoint(
            project_root,
            status="awaiting-action-response",
            remaining_ids=[pp.id for pp in proposals[cursor:]],
            note=f"awaiting action for {p.id}",
            intent_id=_action_intent_id(p.id),
        )

        try:
            action = _action_for(p)
        except PromptAbortedError:
            remaining = [pp.id for pp in proposals[cursor:]]
            _write_checkpoint(
                project_root,
                status="deferred-user-pause",
                remaining_ids=remaining,
                note="user paused mid-loop",
            )
            renderer.write("")
            renderer.write("Pausei. Estado salvo em .claude/.evolve-checkpoint.yaml")
            return 130

        if action == "v":
            _render_proposal_detail(p, index=index, total=total, full=True)
            continue

        if action == "d":
            _record_history_event(project_root, "evolve-defer", p.id)
            cursor += 1
            continue

        if action == "r":
            if not question.confirm(
                f"Rejeitar {p.id} permanentemente (fingerprint vai bloquear "
                "re-proposição)?",
                default=False,
            ):
                continue
            _reject_proposal(project_root, p)
            _record_history_event(project_root, "evolve-reject", p.id)
            renderer.write(renderer.dim(f"  ✓ {p.id} rejeitada permanentemente."))
            cursor += 1
            continue

        if action == "a":
            success = _apply_proposal(project_root, p, cfg)
            if not success:
                remaining = [pp.id for pp in proposals[cursor:]]
                _write_checkpoint(
                    project_root,
                    status="deferred-l2-full",
                    remaining_ids=remaining,
                    note=f"overflow before applying {p.id}",
                )
                choice = _three_paths_overflow(project_root)
                if choice == "a":
                    renderer.write(
                        "  Rode `forge memory` → distill L2, depois `forge evolve`."
                    )
                elif choice == "b":
                    renderer.write("  Pausei. Checkpoint salvo.")
                else:
                    renderer.write("  Abortado pelo usuário.")
                return 0
            _record_history_event(
                project_root,
                "evolve-apply",
                p.id,
                extras={"l2-size-after-bytes": l2_size_bytes(project_root)},
            )
            cursor += 1
            continue

        # Unknown action — defensive.
        cursor += 1

    # ── Done ────────────────────────────────────────────────────────────────
    _clear_checkpoint(project_root)
    renderer.write("")
    renderer.write(renderer.colored("✓ Fim da rodada de evolve.", "green"))
    return 0


__all__ = ["run"]
