"""`forge memory` — interactive memory layer inspector + L2 management.

Read-only by default. Mutations (`forget L2 entry`, manual `distill L2`)
require explicit double confirmation. Manual distill is only meaningful
when L2 is over `max-size-mb` — discipline §6 says auto-distill mid-apply
is forbidden, so the user reaches it via this menu after `forge evolve`
parks itself with `deferred-l2-full`.

Export option dumps `export_for_context_pack(...)` to stdout — that's the
single intentional non-renderer write in the engine (consumer pipes it
into a context-pack file).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from engine.memory.distiller import (
    apply_proposal_to_l2,
    detect_l2_overflow,
    read_proposals_queue,
)
from engine.memory.l1 import (
    list_active_features,
    list_archived_features,
    read_ambiguity_map,
    read_history,
    read_hypothesis,
    read_l1_status,
    read_rationale_trace,
)
from engine.memory.l2 import (
    L2Entry,
    export_for_context_pack,
    l2_size_bytes,
    read_l2,
    remove_entry as l2_remove_entry,
)
from engine.memory.l3 import read_l3_entry, read_l3_index
from engine.ui import question, renderer
from engine.ui.question import PromptAbortedError
from engine.ui.tree import render_tree
from engine.utils.paths import (
    ProjectRootNotFoundError,
    claude_dir,
    ensure_dir,
    find_project_root,
    memory_l2_path,
    workflow_config_path,
)
from engine.utils.yaml_io import read_yaml_or_default, write_yaml
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    load_yaml_checkpoint as _load_yaml_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso as _utc_now_iso_shared

_PAGE_SIZE = 10


# ── Checkpoint (DRIFT-1 W2.T3b — intent-resume, outcome C) ───────────────────
#
# Per the T3a audit (.planning/drift-1/checkpoint-audit.json,
# action="add-new", reuse_path="init-pattern"), memory_cli ganha um
# checkpoint pra cobrir os 11 callsites interativos (menu ask + prompts
# em inspect-L1/inspect-L3, search, forget L2 com 2 confirms, distill
# L2). Mirrors ``_InitCheckpoint`` (engine/init.py:100-108) — outcome
# C, sem import de ``engine.qa.checkpoint`` (Decision 22).
#
# Refs:
#   - docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
#   - engine/init.py:100-108 (canonical template)


@dataclass
class _MemoryCliCheckpoint:
    """State serialized before each ``question.ask*`` call in ``memory_cli.run``.

    Carrega ``submenu`` (1..7) e ``entry_id`` opcional pra recuperar
    o ponto exato do fluxo apos exit-2 + re-invoke. Submenus podem ter
    multiplos prompts em cadeia (distill L2 itera por propostas).
    """

    step: str
    at: str
    project_root: str
    intent_id: str | None = None
    submenu: str | None = None
    entry_id: str | None = None


def _memory_cli_checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / ".memory-cli-checkpoint.yaml"


# Os 4 helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` +
# ``engine.utils.iso`` — consolidação dos 30 duplicates + 10 cópias de
# ``_utc_now_iso_*`` apontada pelos findings #5 e #21 do master review do
# PR #11. Os nomes ``_save_memory_cli_checkpoint`` etc. permanecem como API
# privada do módulo para preservar os contracts dos testes em
# ``tests/unit/test_engine_memory_cli_resume.py`` (Mandamento #2 — verde).


def _save_memory_cli_checkpoint(cp: _MemoryCliCheckpoint) -> None:
    """Persist the memory_cli checkpoint atomically."""
    _save_yaml_checkpoint_io(
        _memory_cli_checkpoint_path(Path(cp.project_root)),
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "intent-id": cp.intent_id,
            "submenu": cp.submenu,
            "entry-id": cp.entry_id,
        },
    )


def _load_memory_cli_checkpoint(project_root: Path) -> dict[str, Any] | None:
    """Read the memory_cli checkpoint, returning ``None`` when absent."""
    return _load_yaml_checkpoint_io(_memory_cli_checkpoint_path(project_root))


def _clear_memory_cli_checkpoint(project_root: Path) -> None:
    """Remove the checkpoint — best-effort; silent on OSError (idempotent)."""
    _clear_checkpoint_io(_memory_cli_checkpoint_path(project_root))


def _utc_now_iso_memory_cli() -> str:
    """ISO-8601 UTC timestamp — thin shim sobre ``engine.utils.iso``."""
    return _utc_now_iso_shared()


def _load_workflow_config(project_root: Path) -> dict[str, Any]:
    cfg = read_yaml_or_default(workflow_config_path(project_root), {})
    return cfg if isinstance(cfg, dict) else {}


# ── Inspect L2 ──────────────────────────────────────────────────────────────


def _inspect_l2(project_root: Path) -> None:
    entries = read_l2(project_root)
    if not entries:
        renderer.write(renderer.dim("  L2 vazia."))
        return

    size_kb = l2_size_bytes(project_root) / 1024
    renderer.write("")
    renderer.write(
        renderer.bold(f"L2-project.yaml — {len(entries)} entradas, {size_kb:.1f} KB")
    )
    renderer.write("")

    total = len(entries)
    cursor = 0
    while cursor < total:
        page = entries[cursor : cursor + _PAGE_SIZE]
        for i, e in enumerate(page, start=cursor + 1):
            prov = ", ".join(e.provenance) if e.provenance else "—"
            renderer.write(
                f"  [{i:>3}] {e.id:<10} {e.kind:<16} conf={e.confidence:.2f}  "
                f"{(e.title or '')[:42]}"
            )
            renderer.write(renderer.dim(f"        provenance: {prov}"))
        cursor += _PAGE_SIZE
        if cursor < total:
            try:
                cont = question.confirm(
                    f"Mostrar mais {min(_PAGE_SIZE, total - cursor)} de {total}?",
                    default=True,
                )
            except PromptAbortedError:
                break
            if not cont:
                break


# ── Inspect L1 ──────────────────────────────────────────────────────────────


def _inspect_l1(project_root: Path) -> None:
    active = list_active_features(project_root)
    archived = list_archived_features(project_root)
    all_slugs = sorted(set(active) | set(archived))
    if not all_slugs:
        renderer.write(renderer.dim("  Sem features em L1."))
        return

    options = {str(i): s for i, s in enumerate(all_slugs, start=1)}
    options["c"] = "cancelar"
    pick = question.ask(
        "Qual feature?", options, default="1", allow_pause=True
    )
    if pick == "c":
        return
    slug = options[pick]

    state = read_l1_status(slug, project_root)
    hyp = read_hypothesis(slug, project_root)
    amb = read_ambiguity_map(slug, project_root)
    rat = read_rationale_trace(slug, project_root)
    history = read_history(slug, project_root, tail=10)

    tree: dict[str, Any] = {
        "feature": slug,
        "status": (state.status if state else "(arquivada)"),
        "last-action": (state.last_action_kind if state else "—"),
        "hypothesis": hyp if hyp else "—",
        "ambiguity-map": amb if amb else "—",
        "rationale-trace": rat if rat else "—",
        "recent-history": history if history else "—",
    }
    renderer.write("")
    renderer.write(renderer.section_header(f"L1: {slug}", width=78))
    renderer.write("")
    renderer.write(render_tree(tree))


# ── Inspect L3 ──────────────────────────────────────────────────────────────


def _inspect_l3() -> None:
    index = read_l3_index()
    if not index:
        renderer.write(renderer.dim("  MEMORY.md ausente ou vazio."))
        return
    renderer.write("")
    renderer.write(renderer.bold(f"L3 auto-memory — {len(index)} entradas"))
    renderer.write("")
    for i, entry in enumerate(index, start=1):
        renderer.write(f"  [{i:>2}] {entry['title']}")
        renderer.write(renderer.dim(f"       {entry['hook']}"))
    renderer.write("")
    if not question.confirm("Abrir uma entrada específica?", default=False):
        return
    options = {str(i): entry["title"] for i, entry in enumerate(index, start=1)}
    options["c"] = "cancelar"
    pick = question.ask("Qual?", options, default="1", allow_pause=True)
    if pick == "c":
        return
    target = index[int(pick) - 1]
    body = read_l3_entry(target["file"])
    if not body:
        renderer.write(renderer.colored("  arquivo não acessível.", "yellow"))
        return
    renderer.write("")
    renderer.write(renderer.section_header(target["title"], width=78))
    renderer.write("")
    if body.get("frontmatter"):
        renderer.write(render_tree({"frontmatter": body["frontmatter"]}))
    for line in (body.get("body") or "").splitlines():
        renderer.write(f"  {line}")


# ── Search ──────────────────────────────────────────────────────────────────


def _search_all(project_root: Path) -> None:
    needle = question.ask_text("Termo a buscar (substring):").strip().casefold()
    if not needle:
        return

    results_l2: list[tuple[float, str]] = []
    for e in read_l2(project_root):
        score = 0.0
        if needle in (e.title or "").casefold():
            score += 2.0
        if needle in (e.body or "").casefold():
            score += 1.0
        if score > 0:
            results_l2.append((score, f"L2 · {e.id} — {e.title}"))

    results_l1: list[tuple[float, str]] = []
    for slug in list_active_features(project_root):
        hyp = read_hypothesis(slug, project_root) or {}
        amb = read_ambiguity_map(slug, project_root) or {}
        blob = (str(hyp) + " " + str(amb)).casefold()
        if needle in blob:
            results_l1.append((1.0, f"L1 · {slug}"))

    results_l3: list[tuple[float, str]] = []
    for entry in read_l3_index():
        if (
            needle in entry["title"].casefold()
            or needle in entry["hook"].casefold()
        ):
            results_l3.append((1.5, f"L3 · {entry['title']}"))

    all_results = sorted(
        results_l2 + results_l1 + results_l3,
        key=lambda item: item[0],
        reverse=True,
    )
    renderer.write("")
    if not all_results:
        renderer.write(renderer.dim("  sem matches."))
        return
    renderer.write(renderer.bold(f"matches ({len(all_results)})"))
    for _, line in all_results:
        renderer.write(f"  · {line}")


# ── Forget L2 entry ─────────────────────────────────────────────────────────


def _forget_l2(project_root: Path) -> None:
    entries = read_l2(project_root)
    if not entries:
        renderer.write(renderer.dim("  L2 vazia."))
        return
    entry_id = question.ask_text("ID da entrada (ex.: L2-007):").strip()
    target: Optional[L2Entry] = next(
        (e for e in entries if e.id == entry_id), None
    )
    if target is None:
        renderer.write(renderer.colored("  ID não encontrado em L2.", "yellow"))
        return
    renderer.write(f"  alvo: {target.id} — {target.title}")
    if not question.confirm("Apagar essa entrada? (1ª)", default=False):
        return
    if not question.confirm("Confirma — sem restauração. (2ª)", default=False):
        return
    l2_remove_entry(project_root, entry_id)
    renderer.write(renderer.colored(f"  ✓ {entry_id} removida de L2.", "green"))


# ── Distill (manual) ────────────────────────────────────────────────────────


def _distill_l2(project_root: Path) -> None:
    """Detect overflow + apply queued DistillationProposals one by one.

    Algorithm v1 (per discipline §5 single-by-single apply):

    - ``distill-l2``: apply one proposal — adds a new consolidated L2 entry
      and (when payload declares ``obsoletes``) the source entries are marked
      so the next read sees them as obsoleted-by the new entry. v1 keeps
      this conservative: `apply_proposal_to_l2` already handles the L2 write
      for the consolidated promote, and the user-facing flow surfaces one
      proposal at a time.
    - ``consolidate-l2``: merge entries with the same ``kind`` and similar
      ``title`` (substring/keyword match) into a single L2 entry with a
      widened provenance. Delegated to `apply_proposal_to_l2` for the L2
      write — caller approves each proposal explicitly.

    Distillation auto-trigger lives in the retrospective-agent flow; this
    interactive menu is the manual escape hatch.
    """
    cfg = _load_workflow_config(project_root)
    if not detect_l2_overflow(project_root, cfg):
        renderer.write(renderer.dim(
            "  L2 ainda não excede max-size-mb — distill manual não é "
            "necessário (auto roda em feature-done)."
        ))
        renderer.write(renderer.dim(
            "  Distillation auto-gerada acontece via retrospective-agent "
            "ou L2 overflow detectado em runtime."
        ))
        if not question.confirm("Forçar distill mesmo assim?", default=False):
            return

    proposals = [
        p for p in read_proposals_queue(project_root)
        if p.kind in {"distill-l2", "consolidate-l2"}
    ]
    if not proposals:
        renderer.write(renderer.dim(
            "  Nenhuma proposta de distillation/consolidation na queue."
        ))
        renderer.write(renderer.dim(
            "  Distillation auto-gerada acontece via retrospective-agent "
            "ou L2 overflow detectado em runtime."
        ))
        return

    renderer.write(renderer.bold(f"propostas de distill ({len(proposals)})"))
    for i, p in enumerate(proposals, start=1):
        renderer.write(
            f"  [{i:>2}] {p.id}  conf={p.confidence:.2f}  {p.title[:48]}"
        )

    # Single-by-single apply (discipline §5) — same pattern usado por evolve.py
    for p in proposals:
        renderer.write("")
        renderer.write(renderer.section_header(p.id, width=78))
        for line in (p.description or "").splitlines() or ["—"]:
            renderer.write(f"  {line}")
        action = question.ask(
            f"O que fazer com {p.id}?",
            {"a": "aplicar", "d": "depois", "s": "sair"},
            default="d",
            allow_pause=True,
        )
        if action == "s":
            return
        if action == "a":
            apply_proposal_to_l2(project_root, p)
            renderer.write(renderer.colored(f"  ✓ aplicado {p.id}.", "green"))


# ── Export ──────────────────────────────────────────────────────────────────


def _export_l2(project_root: Path) -> None:
    md = export_for_context_pack(project_root)
    # Single intentional direct stdout write — caller may pipe into a file.
    sys.stdout.write(md)
    sys.stdout.flush()


# ── Entry point ─────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:
    """Interactive memory menu."""
    _ = argv

    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge memory: {exc}\n")
        return 2

    # Hint when L2 file just doesn't exist yet.
    if not memory_l2_path(project_root).exists():
        renderer.write(renderer.dim("  (L2-project.yaml ainda não existe)"))

    renderer.write(renderer.bold("forge memory — layers:"))
    options = {
        "1": "inspect L2-project          (paginated)",
        "2": "inspect L1 {slug}",
        "3": "inspect L3 auto-memory      (MEMORY.md proxy)",
        "4": "search                       (substring L1+L2+L3)",
        "5": "forget L2 entry             (confirm dupla)",
        "6": "distill L2                  (apenas em overflow)",
        "7": "export L2 for context-pack  (stdout)",
        "c": "cancelar",
    }

    # DRIFT-1 W2.T3b — persist checkpoint with the deterministic intent-id
    # for the menu ask BEFORE invoking ``question.ask``. On exit-2 +
    # re-invoke, ``question.ask`` finds the matching forge-response.json
    # and returns the value without re-prompting. Outcome C — per-subcommand
    # dataclass, no import from ``engine.qa.checkpoint``.
    _save_memory_cli_checkpoint(
        _MemoryCliCheckpoint(
            step="step-menu",
            at=_utc_now_iso_memory_cli(),
            project_root=str(project_root),
            intent_id=question.stable_intent_id(
                "ask",
                "O que olhar?",
                options,
                extra={
                    "default": "1",
                    "min-selected": None,
                    "validator-hint": None,
                },
            ),
            submenu=None,
        )
    )

    try:
        choice = question.ask(
            "O que olhar?", options, default="1", allow_pause=True
        )
    except PromptAbortedError:
        return 130

    if choice == "c":
        # DRIFT-1 W2.T3b — clear intent-resume checkpoint on clean completion.
        _clear_memory_cli_checkpoint(project_root)
        return 0

    # DRIFT-1 W2.T3b — atualiza checkpoint pra refletir o submenu escolhido
    # ANTES de invocar o handler. Prompts internos (paginacao, search,
    # confirm em forget L2, distill L2) herdam intent-resume via
    # question.ask* — cada um calcula seu proprio intent-id deterministico
    # quando chamado.
    _save_memory_cli_checkpoint(
        _MemoryCliCheckpoint(
            step=f"step-submenu:{choice}",
            at=_utc_now_iso_memory_cli(),
            project_root=str(project_root),
            intent_id=None,
            submenu=choice,
        )
    )

    try:
        if choice == "1":
            _inspect_l2(project_root)
        elif choice == "2":
            _inspect_l1(project_root)
        elif choice == "3":
            _inspect_l3()
        elif choice == "4":
            _search_all(project_root)
        elif choice == "5":
            _forget_l2(project_root)
        elif choice == "6":
            _distill_l2(project_root)
        elif choice == "7":
            _export_l2(project_root)
    except PromptAbortedError:
        renderer.write("  pausado.")
        _clear_memory_cli_checkpoint(project_root)
        return 130
    except Exception as exc:
        sys.stderr.write(f"forge memory: operação falhou — {exc}\n")
        _clear_memory_cli_checkpoint(project_root)
        return 1

    # DRIFT-1 W2.T3b — clear intent-resume checkpoint on clean completion.
    _clear_memory_cli_checkpoint(project_root)
    return 0


__all__ = ["run"]
