"""`forge memory` — wrapper fino arg-driven sobre o `mem` vendorizado.

W-ROUTE 6a: o handler deixou de ser menu interativo (com checkpoint-resume
do DRIFT-1) e virou um dispatcher stateless de subcomandos que delega ao
substrato `mem` via a fronteira shell (`engine.integrations.mem`). Cada
invocação é stateless — sem prompt pausável, sem checkpoint — então o burden
multi-passo desaparece estruturalmente.

Superfície:
    forge memory search <query>      → mem find
    forge memory inspect [id]        → mem get <id> | mem stats
    forge memory export [--budget N] → mem brief
    forge memory distill [--apply]   → mem evolve

Inspeção de lifecycle (status/phase/history) NÃO vive aqui — é `forge status`
(estado operacional, não memória-de-conhecimento). L3 (proxy de MEMORY.md)
foi removido. Voz: mentor calmo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from engine.integrations.mem import (
    mem_brief,
    mem_evolve,
    mem_find,
    mem_get,
    mem_stats,
)
from engine.ui import output_mode, renderer
from engine.ui.exit_codes import ERR_PROJECT_NOT_FOUND, ERR_USAGE, fail_with_tag
from engine.utils.paths import ProjectRootNotFoundError, find_project_root

_USAGE = (
    "uso: forge memory <ação> [args]\n"
    "  search <query>       busca ranqueada no acervo (mem find)\n"
    "  inspect [id]         corpo de uma nota (mem get) ou stats do acervo\n"
    "  export [--budget N]  índice de alto valor pro context-pack (mem brief)\n"
    "  distill [--apply]    curadoria do acervo (mem evolve)\n"
)


def _emit_degraded(message: str) -> int:
    sys.stderr.write(f"forge memory: {message}\n")
    return 1


def _action_search(project_root: Path, rest: list[str], json_mode: bool) -> int:
    query = " ".join(rest).strip()
    if not query:
        sys.stderr.write("forge memory search: falta <query>.\n")
        return fail_with_tag(ERR_USAGE)
    res = mem_find(project_root, query)
    if not res.ok:
        return _emit_degraded(res.message)
    hits = res.data or []
    if json_mode:
        print(json.dumps(hits, indent=2, default=str))
        return 0
    if not hits:
        renderer.write(renderer.dim("  sem matches."))
        return 0
    renderer.write(renderer.bold(f"matches ({len(hits)})"))
    for h in hits:
        renderer.write(
            f"  {h.get('id', '?'):<28} score={h.get('score', 0):.3f}  "
            f"{h.get('type', ''):<10} {(h.get('title') or '')[:48]}"
        )
    return 0


def _action_inspect(project_root: Path, rest: list[str], json_mode: bool) -> int:
    if rest:
        note_id = rest[0]
        res = mem_get(project_root, note_id)
        if not res.ok:
            return _emit_degraded(res.message)
        if res.data is None:
            if json_mode:
                print(json.dumps(None))
            else:
                renderer.write(
                    renderer.colored(f"  nota {note_id} não encontrada.", "yellow")
                )
            return 0
        if json_mode:
            print(json.dumps(res.data, indent=2, default=str))
            return 0
        note = res.data
        renderer.write("")
        renderer.write(renderer.section_header(note.get("title") or note_id, width=78))
        renderer.write(
            renderer.dim(
                f"  {note.get('id', '')} · {note.get('type', '')} · "
                f"imp={note.get('importance', '?')}"
            )
        )
        renderer.write("")
        for line in (note.get("body") or "").splitlines():
            renderer.write(f"  {line}")
        return 0

    res = mem_stats(project_root)
    if not res.ok:
        return _emit_degraded(res.message)
    stats = res.data or {}
    if json_mode:
        print(json.dumps(stats, indent=2, default=str))
        return 0
    renderer.write("")
    renderer.write(renderer.bold("acervo (mem stats)"))
    renderer.write(
        f"  total={stats.get('total', 0)}  live={stats.get('live', 0)}  "
        f"stale={stats.get('stale', 0)}"
    )
    for t, n in sorted((stats.get("by_type") or {}).items()):
        renderer.write(f"    {t:<12} {n}")
    renderer.write(
        f"  inbox: pending={stats.get('inbox_pending', 0)} "
        f"promoted={stats.get('inbox_promoted', 0)} "
        f"rejected={stats.get('inbox_rejected', 0)}"
    )
    return 0


def _action_export(project_root: Path, rest: list[str], json_mode: bool) -> int:
    budget: int | None = None
    if "--budget" in rest:
        idx = rest.index("--budget")
        if idx + 1 >= len(rest):
            sys.stderr.write("forge memory export: --budget exige um inteiro.\n")
            return fail_with_tag(ERR_USAGE)
        try:
            budget = int(rest[idx + 1])
        except ValueError:
            sys.stderr.write("forge memory export: --budget exige um inteiro.\n")
            return fail_with_tag(ERR_USAGE)
    res = mem_brief(project_root, budget=budget)
    if not res.ok:
        return _emit_degraded(res.message)
    items = res.data or []
    if json_mode:
        print(json.dumps(items, indent=2, default=str))
        return 0
    # Texto pro context-pack — stdout direto, pipeable.
    for it in items:
        sys.stdout.write(f"- [{it.get('type', '')}] {it.get('line', '')}\n")
    sys.stdout.flush()
    return 0


def _action_distill(project_root: Path, rest: list[str], json_mode: bool) -> int:
    apply = "--apply" in rest
    res = mem_evolve(project_root, apply=apply)
    if not res.ok:
        return _emit_degraded(res.message)
    data = res.data or {}
    if json_mode:
        print(json.dumps(data, indent=2, default=str))
        return 0
    archive = data.get("archive") or []
    dups = data.get("dup_clusters") or []
    renderer.write("")
    renderer.write(renderer.bold("curadoria do acervo (mem evolve)"))
    renderer.write(
        f"  archive-candidatos={len(archive)}  dup-clusters={len(dups)}  "
        f"aplicados={data.get('applied', 0)}"
    )
    if not apply and (archive or dups):
        renderer.write(
            renderer.dim(
                "  rode `forge memory distill --apply` pra arquivar candidatos "
                "own-author."
            )
        )
    return 0


_ACTIONS = {
    "search": _action_search,
    "inspect": _action_inspect,
    "export": _action_export,
    "distill": _action_distill,
}


def run(argv: list[str]) -> int:
    """Dispatcher arg-driven do `forge memory` (stateless, sem prompt).

    `find_project_root()` vem PRIMEIRO: pré-init (dir sem projeto) → exit 1
    (contrato Bug U1/SPEC §3 A.1), antes de qualquer parse de ação. `--json`
    é meta-flag global já resolvida em `cli.main` (contextvar via
    `output_mode.is_json_mode()`); filtramos do argv aqui pra não poluir os
    args posicionais — `cli.main` repassa `argv[1:]` sem strip.
    """
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge memory: {exc}\n")
        return fail_with_tag(ERR_PROJECT_NOT_FOUND)
    argv = [a for a in argv if a != "--json"]
    if not argv:
        sys.stderr.write(_USAGE)
        return fail_with_tag(ERR_USAGE)
    action, rest = argv[0], argv[1:]
    handler = _ACTIONS.get(action)
    if handler is None:
        sys.stderr.write(f"forge memory: ação desconhecida '{action}'.\n")
        sys.stderr.write(_USAGE)
        return fail_with_tag(ERR_USAGE)
    return handler(project_root, rest, output_mode.is_json_mode())


__all__ = ["run"]
