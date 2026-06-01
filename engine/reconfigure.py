"""`forge reconfigure` — single entrypoint for ANY post-init mutation.

Lock check → snapshot → category menu → submenu per category → diff preview →
confirm → backup → write → append history → auto-doctor quick.

Decision 9 (12 commands) + 10 (zero flags) — every operation that *feels*
like a new verb (card add, inventory refresh, graph rebuild) is a menu
option inside this module.

Resume: if `.claude/.reconfigure-draft.yaml` exists from a previous cancelled
run, we auto-detect it and offer to continue (no flag, per the migration
table in `docs/design/06-command-surface.md`).

Discipline §3: every mutation is preceded by a `.bak` next to the original.
Discipline §7: Ctrl+C / `para` pauses (draft is saved to disk before exit).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.cards.loader import CardError, CardManifest, load_all_cards, load_card
from engine.cards.resolver import resolve
from engine.cards.snapshotter import (
    compute_directory_sha256,
    remove_snapshot,
    snapshot_card,
)
from engine.graph.builder import build_full
from engine.inventory import (
    extract_conventions,
    extract_design_system,
    extract_i18n,
    write_conventions_inventory,
    write_design_system_inventory,
    write_i18n_inventory,
)
from engine.ui import progress as ui_progress
from engine.ui import question, renderer
from engine.utils.paths import (
    cards_canonical_dir,
    cards_dir,
    claude_dir,
    find_project_root,
    workflow_config_path,
)
from engine.utils.sha256 import file_sha256
from engine.utils.yaml_io import backup_file, read_yaml, write_yaml

_DRAFT_NAME = ".reconfigure-draft.yaml"
_HISTORY_NAME = "workflow-config-history.jsonl"
_DEFAULT_BAK_RETENTION_DAYS = 7


# ── Entry point ──────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:
    """Single entrypoint for every post-init mutation.

    Detects `.claude/.reconfigure-draft.yaml` for resume. Argv is ignored
    (decision 10 — zero flags).
    """
    del argv

    try:
        project_root = find_project_root()
    except Exception as exc:
        renderer.write(renderer.colored(f"forge reconfigure: {exc}", "red"))
        return 2

    config_path = workflow_config_path(project_root)
    if not config_path.is_file():
        renderer.write(
            renderer.colored(
                "Nenhum workflow-config.yaml encontrado — rode `forge init` primeiro.",
                "red",
            )
        )
        return 2

    try:
        current = read_yaml(config_path) or {}
    except Exception as exc:
        renderer.write(renderer.colored(f"config inválido: {exc}", "red"))
        return 2

    draft_path = claude_dir(project_root) / _DRAFT_NAME
    draft = _load_draft(draft_path)
    if draft is not None:
        if question.confirm(
            "Detectei um draft de reconfigure não aplicado. Retomar?",
            default=True,
        ):
            working = draft
        else:
            draft_path.unlink(missing_ok=True)
            working = deepcopy(current)
    else:
        working = deepcopy(current)

    _show_snapshot(current)

    categories = _choose_categories()
    if not categories:
        renderer.write("Nada selecionado — saindo sem mudar nada.")
        return 0

    try:
        for cat in categories:
            handler = _CATEGORY_HANDLERS.get(cat)
            if handler is None:
                continue
            handler(project_root, current, working)
            _save_draft(draft_path, working)
    except question.PromptAbortedError:
        _save_draft(draft_path, working)
        renderer.write(
            "Pausei. Draft salvo em .claude/.reconfigure-draft.yaml — "
            "rode `forge reconfigure` de novo pra retomar."
        )
        return 130

    if working == current:
        renderer.write("Nenhuma mudança detectada — saindo sem escrever nada.")
        draft_path.unlink(missing_ok=True)
        return 0

    _show_diff(current, working)
    if not question.confirm("Aplicar essas mudanças?", default=False):
        renderer.write(
            "Cancelado. Draft salvo em .claude/.reconfigure-draft.yaml."
        )
        _save_draft(draft_path, working)
        return 0

    before_sha = file_sha256(config_path)
    backup_file(config_path)
    write_yaml(config_path, working, atomic=True)
    after_sha = file_sha256(config_path)

    _append_history(
        project_root,
        before_sha=before_sha,
        after_sha=after_sha,
        notes=_summarise_changes(current, working),
    )

    draft_path.unlink(missing_ok=True)

    renderer.write("")
    renderer.write(renderer.colored("Reconfigure aplicado.", "green"))
    _run_quick_doctor(project_root, working)
    return 0


# ── Snapshot view ────────────────────────────────────────────────────────────


def _show_snapshot(config: dict[str, Any]) -> None:
    """Pre-edit read-only summary — never lies."""
    identity = config.get("identity") or {}
    cards_active = (config.get("cards") or {}).get("active") or []
    persona = config.get("persona") or {}
    backend = config.get("backend") or {}

    lines = [
        f"Projeto:       {identity.get('project-name', '—')} · {identity.get('project-slug', '—')}",
        f"Preset:        {identity.get('preset', '—')} (immutable via reconfigure)",
        f"Plataformas:   {', '.join((config.get('platforms') or {}).get('active', []) or ['—'])}",
        f"Cards ativos:  {len(cards_active)}",
    ]
    if cards_active:
        names = [c.get("name", "?") for c in cards_active]
        lines.append("               " + " · ".join(names))
    lines.append(f"Backend:       {backend.get('provider', '—')}")
    lines.append(
        f"Persona:       {persona.get('name', '—')} · "
        f"drill-down: {persona.get('drill-down-aggressiveness', '—')}"
    )
    renderer.write("")
    renderer.write(renderer.box("Configuração atual", lines))


# ── Category menu ────────────────────────────────────────────────────────────


def _choose_categories() -> list[str]:
    options = {
        "cards":          "add/remove/upgrade/lock/inspect",
        "paths":          "feature-roots, tests-roots",
        "conventions":    "DI, navigation, folder layout, naming",
        "backend":        "ticketing, external-docs",
        "persona":        "comportamento do mentor",
        "memory":         "L2 distill manual, retention",
        "hooks":          "regenerar",
        "inventory":      "re-extrair DS/i18n/conventions",
        "graph":          "rebuild full",
        "cleanup-bak":    "remover .bak overdue",
        "external-deps":  "marcar dep externa como resolvida",
    }
    return question.ask_multi(
        "O que mudar? (multi-select, vazio = sair sem mudar)",
        options,
        min_selected=0,
    )


# ── Category handlers ───────────────────────────────────────────────────────


def _handle_cards(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    action = question.ask(
        "Cards — qual ação?",
        {
            "add":     "adicionar card",
            "remove":  "remover card",
            "upgrade": "atualizar card do canonical",
            "lock":    "travar (pin) versão atual",
            "inspect": "inspecionar card (read-only)",
        },
        default="add",
    )
    if action == "add":
        _cards_add(project_root, working)
    elif action == "remove":
        _cards_remove(project_root, working)
    elif action == "upgrade":
        _cards_upgrade(project_root, working)
    elif action == "lock":
        _cards_lock(working)
    elif action == "inspect":
        _cards_inspect(project_root, working)


def _cards_add(project_root: Path, working: dict[str, Any]) -> None:
    active_names = {c.get("name") for c in _active_cards(working)}
    canonical = cards_canonical_dir()
    candidates: list[CardManifest] = []
    try:
        all_cards = load_all_cards(canonical)
    except CardError as exc:
        renderer.write(renderer.colored(f"erro lendo canonical: {exc}", "red"))
        return
    for c in all_cards:
        if c.name not in active_names:
            candidates.append(c)
    if not candidates:
        renderer.write("Todos os cards do canonical já estão ativos.")
        return

    opts = {c.name: f"{c.description} ({c.category})" for c in candidates}
    picked = question.ask_multi(
        "Cards disponíveis para adicionar:", opts, min_selected=1
    )
    if not picked:
        return

    # Resolver check: build the full hypothetical set.
    project_cards_root = cards_dir(project_root)
    active_manifests: list[CardManifest] = _load_active_manifests(project_cards_root)
    to_add = [c for c in candidates if c.name in picked]
    hypothetical = active_manifests + to_add
    result = resolve(hypothetical)
    if result.errors:
        renderer.write(renderer.colored("Resolver bloqueou:", "red"))
        for err in result.errors:
            renderer.write(f"  · {err}")
        return

    # Stage snapshots + entries in working config.
    entries = list((working.get("cards") or {}).get("active") or [])
    for card in to_add:
        snap_dir = project_cards_root / card.name
        sha = snapshot_card(card.source_path, snap_dir)
        entries.append({"name": card.name, "sha256": sha, "pinned": False})
        renderer.write(renderer.colored(f"  + {card.name} ({sha[:12]}…)", "green"))
    working.setdefault("cards", {})["active"] = entries


def _cards_remove(project_root: Path, working: dict[str, Any]) -> None:
    active = _active_cards(working)
    if not active:
        renderer.write("Sem cards ativos para remover.")
        return
    opts = {c.get("name"): c.get("name") for c in active}
    picked = question.ask_multi("Cards a remover:", opts, min_selected=1)
    if not picked:
        return

    project_cards_root = cards_dir(project_root)
    active_manifests = _load_active_manifests(project_cards_root)
    remaining = [c for c in active_manifests if c.name not in picked]
    result = resolve(remaining)
    if result.errors:
        renderer.write(renderer.colored(
            "Resolver bloqueia remoção — outro card depende:", "red"
        ))
        for err in result.errors:
            renderer.write(f"  · {err}")
        return

    for name in picked:
        snap_dir = project_cards_root / name
        if snap_dir.exists():
            shutil.move(str(snap_dir), str(snap_dir.with_name(name + ".bak")))
        renderer.write(renderer.colored(f"  - {name} (snapshot → .bak)", "yellow"))
    working.setdefault("cards", {})["active"] = [
        c for c in (working.get("cards") or {}).get("active") or []
        if c.get("name") not in picked
    ]


def _cards_upgrade(project_root: Path, working: dict[str, Any]) -> None:
    active = _active_cards(working)
    if not active:
        renderer.write("Sem cards ativos.")
        return
    canonical = cards_canonical_dir()
    upgradable: list[tuple[str, str, str]] = []
    for entry in active:
        name = entry.get("name")
        canonical_dir = canonical / name
        if not canonical_dir.is_dir():
            continue
        new_sha = compute_directory_sha256(canonical_dir)
        old_sha = entry.get("sha256", "")
        if new_sha != old_sha:
            upgradable.append((name, old_sha, new_sha))
    if not upgradable:
        renderer.write("Todos os snapshots batem com o canonical — nada a atualizar.")
        return

    opts = {
        name: f"{old[:8]}… → {new[:8]}…" for name, old, new in upgradable
    }
    picked = question.ask_multi("Cards para upgrade:", opts, min_selected=1)
    project_cards_root = cards_dir(project_root)
    for name, _old, new_sha in upgradable:
        if name not in picked:
            continue
        snap_dir = project_cards_root / name
        sha = snapshot_card(canonical / name, snap_dir)
        for e in (working.get("cards") or {}).get("active") or []:
            if e.get("name") == name:
                e["sha256"] = sha
        renderer.write(renderer.colored(f"  ↑ {name} ({sha[:12]}…)", "green"))


def _cards_lock(working: dict[str, Any]) -> None:
    active = _active_cards(working)
    if not active:
        return
    opts = {
        c.get("name"): "pinned" if c.get("pinned") else "unpinned" for c in active
    }
    picked = question.ask_multi(
        "Cards para travar (pin = não sugere upgrade):", opts, min_selected=1
    )
    for entry in (working.get("cards") or {}).get("active") or []:
        if entry.get("name") in picked:
            entry["pinned"] = True
            renderer.write(renderer.colored(f"  📌 {entry['name']} pinned", "cyan"))


def _cards_inspect(project_root: Path, working: dict[str, Any]) -> None:
    active = _active_cards(working)
    if not active:
        return
    opts = {c.get("name"): c.get("name") for c in active}
    choice = question.ask("Qual card inspecionar?", opts)
    snap = cards_dir(project_root) / choice
    try:
        card = load_card(snap)
    except CardError as exc:
        renderer.write(renderer.colored(str(exc), "red"))
        return
    sha = compute_directory_sha256(snap) if snap.is_dir() else "—"
    lines = [
        f"name:        {card.name}",
        f"version:     {card.version}",
        f"category:    {card.category}",
        f"maturity:    {card.maturity}",
        f"sha256:      {sha[:16]}…",
        f"provides:    {', '.join(card.provides)}",
        f"requires:    {', '.join(card.requires) or '—'}",
        f"contribs:    templates={len(card.contributes.get('templates') or [])} "
        f"validators={len(card.contributes.get('validators') or [])} "
        f"hooks={len(card.contributes.get('hooks') or [])}",
    ]
    renderer.write(renderer.box(f"Card · {card.name}", lines))


def _handle_paths(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    del project_root, current
    paths = working.setdefault("paths", {})
    roots = paths.setdefault("feature-roots", {})
    for platform in ("android", "ios", "shared", "web"):
        cur = roots.get(platform, "")
        new = question.ask_text(
            f"feature-roots.{platform}",
            default=cur or "—",
        )
        if new and new != "—":
            roots[platform] = new


def _handle_conventions(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    del project_root, current
    conv = working.setdefault("conventions", {})
    fields = {
        "di-pattern":         "DI pattern (koin-annotations|hilt|manual)",
        "navigation-android": "nav android (nav3|nav2|custom)",
        "navigation-ios":     "nav ios (swiftui-navigation|uikit)",
        "folder-layout":      "folder layout (free-form)",
    }
    for key, label in fields.items():
        cur = conv.get(key, "")
        val = question.ask_text(f"{label} [{cur or '—'}]", default=cur or "")
        if val:
            conv[key] = val


def _handle_backend(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    del project_root, current
    backend = working.setdefault("backend", {})
    provider = question.ask_text(
        "backend.provider (firebase|rest|graphql|...)",
        default=backend.get("provider", "") or "",
    )
    if provider:
        backend["provider"] = provider
    ticketing = working.setdefault("ticketing", {})
    if question.confirm("Editar ticketing?", default=False):
        for key in ("provider", "workspace", "default-project"):
            val = question.ask_text(
                f"ticketing.{key}", default=ticketing.get(key, "") or ""
            )
            if val:
                ticketing[key] = val


def _handle_persona(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    del project_root, current
    persona = working.setdefault("persona", {})
    drill = question.ask(
        "persona.drill-down-aggressiveness",
        {"low": "low", "medium": "medium", "high": "high"},
        default=persona.get("drill-down-aggressiveness", "medium"),
    )
    persona["drill-down-aggressiveness"] = drill
    closing = question.ask(
        "persona.closing-style",
        {"silent": "silent", "brief": "brief", "didactic": "didactic", "expressive": "expressive"},
        default=persona.get("closing-style", "didactic"),
    )
    persona["closing-style"] = closing


def _handle_memory(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    del project_root, current
    mem = working.setdefault("memory", {}).setdefault("l2", {})
    days = question.ask_text(
        "memory.l2.max-size-mb (int, default 1)",
        default=str(mem.get("max-size-mb", 1)),
        validator=lambda s: s.isdigit(),
        validator_hint="Digite um inteiro.",
    )
    mem["max-size-mb"] = int(days)
    if question.confirm("Rodar distill manual de L2 agora?", default=False):
        renderer.write(
            "Distill manual: chama `engine.memory.distiller` quando integrado "
            "(stub aqui — TODO Wave 4 memory commands)."
        )


def _handle_hooks(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    del current, working
    renderer.write("Regenerando hooks…")
    hooks_target = claude_dir(project_root) / "hooks"
    hooks_target.mkdir(parents=True, exist_ok=True)
    renderer.write(renderer.colored(
        "  · hooks dir tocada. Re-merge real depende de templates/hooks/ "
        "(stub aqui — TODO integrar com cards.merger).",
        "yellow",
    ))


def _handle_inventory(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    del current, working
    targets = question.ask_multi(
        "Quais inventários re-extrair?",
        {"ds": "design-system", "i18n": "i18n keys", "conv": "conventions"},
        min_selected=1,
    )
    if "ds" in targets:
        with ui_progress.spinner("extraindo design-system"):
            inv = extract_design_system(project_root)
        write_design_system_inventory(project_root, inv)
        renderer.write(renderer.colored("  ✓ inventory/design-system.yaml", "green"))
    if "i18n" in targets:
        with ui_progress.spinner("extraindo i18n"):
            inv = extract_i18n(project_root)
        write_i18n_inventory(project_root, inv)
        renderer.write(renderer.colored("  ✓ inventory/i18n.yaml", "green"))
    if "conv" in targets:
        with ui_progress.spinner("extraindo conventions"):
            inv = extract_conventions(project_root)
        write_conventions_inventory(project_root, inv)
        renderer.write(renderer.colored("  ✓ inventory/conventions.yaml", "green"))


def _handle_graph(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    del current, working
    if not question.confirm("Rebuild full do graph (pode demorar)?", default=False):
        return
    renderer.write("Rebuilding graph…")

    def _cb(stage: str, done: int, total: int) -> None:
        if total > 0 and done % max(1, total // 20) == 0:
            renderer.write(f"  {stage}: {done}/{total}")

    stats = build_full(project_root, progress_cb=_cb)
    renderer.write(renderer.colored(
        f"  ✓ {stats['files_scanned']} files · "
        f"{stats['symbols_extracted']} symbols · "
        f"{stats['edges_created']} edges · "
        f"{stats['duration_ms']}ms",
        "green",
    ))

    # Refresh reuse-intelligence proposals against the new graph state.
    try:
        from engine.graph.duplicates import queue_proposals_from_table

        n_queued = queue_proposals_from_table(project_root)
        if n_queued:
            renderer.write(renderer.colored(
                f"  ✓ {n_queued} reuse proposal(s) (re)queued — `forge evolve`",
                "green",
            ))
    except Exception as exc:  # never fail reconfigure for a scan hiccup
        renderer.write(
            f"  ⚠ reuse scan errored: {type(exc).__name__}: {exc}"
        )


def _handle_cleanup_bak(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    del current
    retention_days = float(
        ((working.get("cleanup") or {}).get("bak-retention-days"))
        or _DEFAULT_BAK_RETENTION_DAYS
    )
    now = datetime.now(timezone.utc).timestamp()
    overdue: list[Path] = []
    young: list[Path] = []
    for bak in claude_dir(project_root).rglob("*.bak"):
        if not bak.is_file() and not bak.is_dir():
            continue
        try:
            age_days = (now - bak.stat().st_mtime) / 86400.0
        except OSError:
            continue
        if age_days < 1.0:  # §3 — < 24h é hands-off
            continue
        if age_days > retention_days:
            overdue.append(bak)
        else:
            young.append(bak)

    if not overdue:
        renderer.write(f"Sem .bak overdue (retention={retention_days}d, "
                       f"em janela={len(young)}).")
        return
    renderer.write(f"{len(overdue)} .bak overdue (> {retention_days}d):")
    for p in overdue[:20]:
        renderer.write(f"  · {p.relative_to(project_root)}")
    if len(overdue) > 20:
        renderer.write(f"  …(+{len(overdue) - 20})")
    if not question.confirm("Deletar todos os listados?", default=False):
        return
    for p in overdue:
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        except OSError as exc:
            renderer.write(renderer.colored(f"  ! falhou {p}: {exc}", "yellow"))
    renderer.write(renderer.colored(f"  ✓ {len(overdue)} .bak removidos", "green"))


def _handle_external_deps(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    """Discipline §9 — mark an external dependency as resolved.

    Distinct from other reconfigure categories: this writes directly to
    `tasks/TASK-NNNN.yaml` files (not to workflow-config.yaml) and updates
    the per-feature `status.json`. The stage-and-diff flow doesn't apply
    here — diff of "resolved-at: null → timestamp" is binary, user already
    confirmed in the inner prompt.

    Reads `working` only to honor cleanup.bak-retention-days for backups.
    """
    del current, working  # not used; write-now semantics

    from engine.memory.l1 import (
        append_history,
        blocking_deps,
        is_blocked,
        list_active_features,
        read_l1_status,
        write_l1_status,
    )

    # 1. Discover blocked features + tickets.
    candidates: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for slug in list_active_features(project_root):
        deps = blocking_deps(slug, project_root)
        if not deps:
            continue
        # Group by ticket → list of (slug, dep dict)
        for d in deps:
            ticket = str(d.get("ticket") or "?")
            candidates.setdefault(ticket, []).append((slug, d))

    if not candidates:
        renderer.write("")
        renderer.write("Sem deps externas abertas em features ativas.")
        renderer.write(renderer.dim("Nada pra fazer aqui."))
        return

    # 2. Render the catalog.
    renderer.write("")
    renderer.write(renderer.section_header("external dependencies abertas"))
    ticket_options: dict[str, str] = {}
    for ticket, entries in sorted(candidates.items()):
        slugs_str = " · ".join(sorted({slug for slug, _ in entries}))
        integration = entries[0][1].get("integration", "manual")
        n = len(entries)
        suffix = "" if n == 1 else f" ({n} tasks)"
        ticket_options[ticket] = (
            f"{integration} · afeta: {slugs_str}{suffix}"
        )
    ticket_options["cancelar"] = "voltar sem mudar nada"

    chosen = question.ask(
        "Qual ticket marcar como resolvido?",
        ticket_options,
    )
    if chosen == "cancelar":
        renderer.write(renderer.dim("Cancelado — nada gravado."))
        return

    entries = candidates.get(chosen, [])
    if not entries:
        renderer.write(
            renderer.colored(
                f"✋ {chosen} não bateu em nenhuma entry — abortando.",
                "yellow",
            )
        )
        return

    # 3. Confirm.
    affected_summary = "\n".join(
        f"  · {slug}/tasks/{d.get('task', '?')}.yaml"
        f".depends_on_external[ticket={chosen}].resolved-at"
        for slug, d in entries
    )
    renderer.write("")
    renderer.write(f"Vai marcar {chosen} como resolvido em {len(entries)} entry(ies):")
    renderer.write(affected_summary)
    renderer.write("")
    if not question.confirm("Aplicar agora?", default=True):
        renderer.write(renderer.dim("Cancelado — nada gravado."))
        return

    # 4. Apply atomically: backup + write per task file.
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    affected_slugs: set[str] = set()
    files_updated: list[Path] = []
    rollback_log: list[tuple[Path, Path]] = []  # (target, backup)

    try:
        # Group by file path to minimize re-reads.
        by_file: dict[Path, list[dict[str, Any]]] = {}
        for slug, dep in entries:
            from engine.memory.l1 import _feature_tasks_dir as _ft_dir

            tasks_dir = _ft_dir(slug, project_root)
            if tasks_dir is None:
                continue
            task_id = dep.get("task", "?")
            task_path = tasks_dir / f"{task_id}.yaml"
            if not task_path.is_file():
                continue
            by_file.setdefault(task_path, []).append(dep)
            affected_slugs.add(slug)

        for task_path, deps_to_update in by_file.items():
            data = read_yaml(task_path) or {}
            if not isinstance(data, dict):
                continue
            ext_list = (
                data.get("depends_on_external")
                or data.get("depends-on-external")
                or []
            )
            if not isinstance(ext_list, list):
                continue
            mutated = False
            for entry in ext_list:
                if not isinstance(entry, dict):
                    continue
                if entry.get("ticket") != chosen:
                    continue
                already = entry.get("resolved-at") or entry.get("resolved_at")
                if already:
                    continue
                entry["resolved-at"] = now_iso
                mutated = True
            if not mutated:
                continue
            data["depends_on_external"] = ext_list
            backup = backup_file(task_path)
            if backup is not None:
                rollback_log.append((task_path, backup))
            write_yaml(task_path, data, atomic=True)
            files_updated.append(task_path)
            renderer.write(
                renderer.colored(
                    f"  ✓ {task_path.relative_to(project_root)}",
                    "green",
                )
            )

        # 5. Re-evaluate feature state for each affected slug.
        for slug in sorted(affected_slugs):
            st = read_l1_status(slug, project_root)
            if st is None:
                continue
            still_blocked = is_blocked(slug, project_root)
            if st.status == "blocked-on-external" and not still_blocked:
                st.status = "implementing"
                st.last_action_kind = "blocked-external-cleared"
                write_l1_status(st, project_root)
                renderer.write(
                    renderer.colored(
                        f"  ↻ {slug} state: blocked-on-external → implementing",
                        "green",
                    )
                )
            append_history(
                slug,
                project_root,
                {
                    "event": "external-dep-marked-resolved",
                    "ticket": chosen,
                    "files-updated": len(by_file),
                },
            )
    except Exception as exc:
        # Rollback any partial write.
        renderer.write(renderer.colored(f"falha — rolling back: {exc}", "red"))
        for target, backup in rollback_log:
            try:
                if backup.is_file():
                    shutil.copy2(backup, target)
            except OSError:
                pass
        raise

    if not files_updated:
        renderer.write(renderer.colored(
            f"Nenhuma entry foi modificada (todas já tinham resolved-at).",
            "yellow",
        ))


_CATEGORY_HANDLERS = {
    "cards":         _handle_cards,
    "paths":         _handle_paths,
    "conventions":   _handle_conventions,
    "backend":       _handle_backend,
    "persona":       _handle_persona,
    "memory":        _handle_memory,
    "hooks":         _handle_hooks,
    "inventory":     _handle_inventory,
    "graph":         _handle_graph,
    "cleanup-bak":   _handle_cleanup_bak,
    "external-deps": _handle_external_deps,
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _active_cards(config: dict[str, Any]) -> list[dict[str, Any]]:
    return list((config.get("cards") or {}).get("active") or [])


def _load_active_manifests(cards_root: Path) -> list[CardManifest]:
    if not cards_root.is_dir():
        return []
    out: list[CardManifest] = []
    for d in sorted(cards_root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if d.name.endswith(".bak"):
            continue
        if not (d / "card.yaml").is_file():
            continue
        try:
            out.append(load_card(d))
        except CardError:
            continue
    return out


def _show_diff(current: dict[str, Any], working: dict[str, Any]) -> None:
    """Compact diff: key-by-key for top-level + cards.active set diff."""
    renderer.write("")
    renderer.write(renderer.section_header("Plano de diff"))
    keys = sorted(set(current.keys()) | set(working.keys()))
    for key in keys:
        a = current.get(key)
        b = working.get(key)
        if a == b:
            continue
        if key == "cards":
            a_names = {c.get("name") for c in (a or {}).get("active") or []}
            b_names = {c.get("name") for c in (b or {}).get("active") or []}
            removed = sorted(a_names - b_names)
            added = sorted(b_names - a_names)
            if removed:
                renderer.write(renderer.colored(
                    f"  - cards.active: -{','.join(removed)}", "red"
                ))
            if added:
                renderer.write(renderer.colored(
                    f"  + cards.active: +{','.join(added)}", "green"
                ))
            continue
        renderer.write(renderer.colored(f"  - {key}: {_short(a)}", "red"))
        renderer.write(renderer.colored(f"  + {key}: {_short(b)}", "green"))


def _short(value: Any, limit: int = 80) -> str:
    s = json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _summarise_changes(current: dict[str, Any], working: dict[str, Any]) -> str:
    diffs: list[str] = []
    a_cards = {c.get("name") for c in (current.get("cards") or {}).get("active") or []}
    b_cards = {c.get("name") for c in (working.get("cards") or {}).get("active") or []}
    if a_cards != b_cards:
        added = sorted(b_cards - a_cards)
        removed = sorted(a_cards - b_cards)
        if added:
            diffs.append(f"+cards:{','.join(added)}")
        if removed:
            diffs.append(f"-cards:{','.join(removed)}")
    for k in current.keys() | working.keys():
        if k == "cards":
            continue
        if current.get(k) != working.get(k):
            diffs.append(k)
    msg = "; ".join(diffs) or "no-op"
    if len(msg) > 250:
        msg = msg[:247] + "…"
    return msg


def _load_draft(draft_path: Path) -> dict[str, Any] | None:
    if not draft_path.is_file():
        return None
    try:
        data = read_yaml(draft_path)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _save_draft(draft_path: Path, working: dict[str, Any]) -> None:
    try:
        write_yaml(draft_path, working, atomic=True)
    except OSError:
        pass


def _append_history(
    project_root: Path,
    *,
    before_sha: str,
    after_sha: str,
    notes: str,
) -> None:
    """Append a single JSONL line per `docs/schemas/workflow-config-history.md`."""
    entry = {
        "schema-version": 1,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "forge reconfigure",
        "action": "reconfigure-applied",
        "before-snapshot-sha": before_sha,
        "after-snapshot-sha": after_sha,
        "user-confirmed": True,
        "notes": notes,
    }
    path = claude_dir(project_root) / _HISTORY_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass


def _run_quick_doctor(project_root: Path, config: dict[str, Any]) -> None:
    """Minimal post-apply sanity checks — surface but never block here.

    FOLLOWUP: delegate to engine.doctor.run_quick() once that module lands.
    """
    issues: list[str] = []
    for entry in _active_cards(config):
        snap = cards_dir(project_root) / entry.get("name", "")
        if not snap.is_dir():
            issues.append(f"card {entry.get('name')} sem snapshot")
            continue
        expected = entry.get("sha256")
        if expected:
            actual = compute_directory_sha256(snap)
            if actual != expected:
                issues.append(f"sha256 mismatch em {entry.get('name')}")
    if not issues:
        renderer.write(renderer.colored("doctor (quick): passing", "green"))
    else:
        renderer.write(renderer.colored(
            f"doctor (quick): {len(issues)} problema(s)", "yellow"
        ))
        for i in issues:
            renderer.write(f"  · {i}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run(sys.argv[1:]))
