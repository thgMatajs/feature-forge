"""`forge implement` — execution conductor (Plan Mode → Apply → next task).

Single Task Contract per invocation. Walks the user through:

    1. Resolve feature slug + state guard (readiness must be 'ready').
    2. Pick next task via task-breakdown DAG topo-sort + status filter.
    3. Plan Mode: surface contract + bdd_scenarios_covered + allowed_files
       + gates + validations. Block on user 'sim'.
    4. Apply Mode (v1 stub): instruct user/Claude to implement against the
       contract. Out-of-scope edits surface as findings/FND-*.yaml via the
       three-paths block.
    5. Verify + Commit are user-driven in v1 — emit hand-off copy that
       points at `forge verify` + a conventional commit message.

Exit codes:
    0    task acknowledged / parked between tasks
    130  user pause
    other  hard gate violation
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from engine.memory.l1 import (
    L1State,
    acquire_phase_lock,
    append_history,
    read_l1_status,
    release_phase_lock,
    write_l1_status,
)
from engine.persona import mentor_calmo
from engine.ui import question, renderer
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    ensure_dir,
    feature_dir,
    find_project_root,
    workflow_config_path,
)
from engine.utils.yaml_io import read_yaml, read_yaml_or_default

_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,48}[a-z0-9]$")
_TASK_ID_PATTERN = re.compile(r"^TASK-(\d{4})$")


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class TaskContract:
    task_id: str
    path: Path
    description: str
    allowed_files: list[str]
    validations: list[str]
    gates: list[str]
    dependencies: list[str]
    bdd_scenarios: list[str]
    status: str
    raw: dict[str, Any]


# ── Filesystem helpers (mirror plan.py — kept local to avoid import cycle) ───


def _resolve_features_root(project_root: Path) -> Path:
    cfg = read_yaml_or_default(workflow_config_path(project_root), {})
    if isinstance(cfg, dict):
        paths = cfg.get("paths") or {}
        roots = paths.get("feature-roots") if isinstance(paths, dict) else None
        if isinstance(roots, list) and roots:
            head = roots[0]
            if isinstance(head, str):
                return (project_root / head).resolve()
        elif isinstance(roots, str):
            return (project_root / roots).resolve()
    return (project_root / "docs" / "feature-implementation-workflow" / "features").resolve()


def _feature_path(project_root: Path, slug: str) -> Path:
    root = _resolve_features_root(project_root)
    default = (
        project_root / "docs" / "feature-implementation-workflow" / "features"
    ).resolve()
    if root == default:
        return feature_dir(project_root, slug)
    return root / slug


def _is_valid_slug(value: str) -> bool:
    return bool(_SLUG_PATTERN.match(value))


# ── Readiness gate ───────────────────────────────────────────────────────────


def _readiness_from_handoff(handoff: Path) -> Optional[str]:
    if not handoff.exists():
        return None
    try:
        import json

        data = json.loads(handoff.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    verdict = data.get("readiness") or data.get("readiness_verdict") or {}
    if isinstance(verdict, dict):
        status = verdict.get("status")
        if isinstance(status, str):
            return status.strip().lower()
    if isinstance(data.get("status"), str):
        return data["status"].strip().lower()
    return None


def _readiness_from_review(review: Path) -> Optional[str]:
    if not review.exists():
        return None
    text = review.read_text(encoding="utf-8")
    match = re.search(
        r"readiness_verdict\s*:\s*[\s\S]*?status\s*:\s*['\"]?([a-z-]+)['\"]?",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().lower()
    fallback = re.search(
        r"^\s*status\s*:\s*([a-z-]+)\s*$", text, re.IGNORECASE | re.MULTILINE
    )
    return fallback.group(1).strip().lower() if fallback else None


def _check_readiness(feature_path: Path) -> tuple[bool, str]:
    """Return (is_ready, observed_status)."""
    handoff = feature_path / "plan-feature-handoff.json"
    review = feature_path / "implementation-readiness-review.md"
    status = _readiness_from_handoff(handoff) or _readiness_from_review(review) or "unknown"
    return status == "ready", status


# ── Task loading + topo-sort ─────────────────────────────────────────────────


def _load_task_contract(path: Path) -> TaskContract:
    raw = read_yaml(path)
    if not isinstance(raw, dict):
        raise SystemExit(f"forge implement: task file {path} is not a YAML mapping.")
    task_id = str(raw.get("task_id") or raw.get("task-id") or path.stem)
    description = str(raw.get("description") or raw.get("title") or "")
    allowed = raw.get("allowed_files") or raw.get("allowed-files") or []
    if not isinstance(allowed, list):
        allowed = []
    validations = raw.get("validations") or []
    if not isinstance(validations, list):
        validations = []
    gates = raw.get("gates") or []
    if not isinstance(gates, list):
        gates = []
    deps = raw.get("dependencies") or raw.get("depends_on") or []
    if not isinstance(deps, list):
        deps = []
    bdd = raw.get("bdd_scenarios_covered") or raw.get("bdd-scenarios-covered") or []
    if not isinstance(bdd, list):
        bdd = []
    status = str(raw.get("status") or "pending").lower()

    return TaskContract(
        task_id=task_id,
        path=path,
        description=description,
        allowed_files=[str(x) for x in allowed],
        validations=[str(x) for x in validations],
        gates=[str(x) for x in gates],
        dependencies=[str(x) for x in deps],
        bdd_scenarios=[str(x) for x in bdd],
        status=status,
        raw=raw,
    )


def _collect_tasks(feature_path: Path) -> list[TaskContract]:
    tasks_dir = feature_path / "tasks"
    if not tasks_dir.is_dir():
        return []
    files = sorted(p for p in tasks_dir.glob("TASK-*.yaml") if p.is_file())
    return [_load_task_contract(p) for p in files]


def _topo_sort(tasks: list[TaskContract]) -> list[TaskContract]:
    """Stable topological sort by `dependencies`. Cycles raise SystemExit."""
    by_id = {t.task_id: t for t in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()
    order: list[TaskContract] = []

    def _visit(node_id: str, stack: list[str]) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            chain = " → ".join(stack + [node_id])
            raise SystemExit(f"forge implement: dependency cycle detected ({chain})")
        if node_id not in by_id:
            # Dependência declarada apontando pra TASK desconhecida — segue
            # tratando como satisfeita pra não travar o pipeline, mas avisa
            # visivelmente pra usuário corrigir o contrato.
            renderer.write(
                renderer.colored(
                    f"⚠ Dependência desconhecida: {node_id} — "
                    "tratando como satisfeita",
                    "yellow",
                )
            )
            return
        visiting.add(node_id)
        for dep in by_id[node_id].dependencies:
            _visit(dep, stack + [node_id])
        visiting.discard(node_id)
        visited.add(node_id)
        order.append(by_id[node_id])

    for task in tasks:
        _visit(task.task_id, [])
    return order


def _pick_next_task(tasks: list[TaskContract]) -> Optional[TaskContract]:
    done = {t.task_id for t in tasks if t.status == "done"}
    sorted_tasks = _topo_sort(tasks)
    for task in sorted_tasks:
        if task.status == "done":
            continue
        unresolved = [d for d in task.dependencies if d not in done]
        if unresolved:
            continue
        return task
    return None


# ── Plan Mode reveal ─────────────────────────────────────────────────────────


def _print_plan_mode(task: TaskContract, project_root: Path) -> None:
    renderer.write("")
    renderer.write(renderer.bold(f"📋 Plan Mode · {task.task_id}"))
    renderer.write("")
    if task.description:
        renderer.write(f"  {task.description}")
        renderer.write("")

    if task.dependencies:
        renderer.write("  Dependências:")
        for dep in task.dependencies:
            renderer.write(f"    · {dep}")
        renderer.write("")

    renderer.write("  Arquivos no escopo (allowed_files):")
    if task.allowed_files:
        for f in task.allowed_files:
            renderer.write(f"    · {f}")
    else:
        renderer.write(renderer.colored("    (vazio — gate vai recusar Apply)", "yellow"))
    renderer.write("")

    if task.bdd_scenarios:
        renderer.write("  BDD coberto:")
        for s in task.bdd_scenarios:
            renderer.write(f"    · {s}")
        renderer.write("")

    renderer.write("  Validações pós-Apply:")
    if task.validations:
        for v in task.validations:
            renderer.write(f"    · {v}")
    else:
        renderer.write(renderer.dim("    (nenhuma declarada — recomendado revisar contrato)"))
    renderer.write("")

    if task.gates:
        renderer.write("  Gates ativos:")
        for g in task.gates:
            renderer.write(f"    · {g}")
        renderer.write("")


# ── Apply Mode (v1 stub) ─────────────────────────────────────────────────────


def _apply_mode_handoff(task: TaskContract, slug: str, project_root: Path) -> None:
    renderer.write("")
    renderer.write(renderer.bold("⚡ Apply Mode (v1 — handoff manual)"))
    renderer.write("")
    renderer.write(
        f"Implemente {task.task_id} seguindo o contrato. Edite somente "
        "arquivos em `allowed_files`. Quando terminar:"
    )
    renderer.write("")
    renderer.write(f"  1) forge verify {slug}    # roda as validações declaradas")
    renderer.write(f"  2) git add <allowed_files apenas>")
    renderer.write(
        f"     git commit -m '{task.task_id}: {task.description or '<descrição>'}'"
    )
    renderer.write(f"  3) forge implement {slug}  # eu pego a próxima task")
    renderer.write("")
    renderer.write(
        renderer.dim(
            "Se for editar algo fora de allowed_files, pare — vai virar Finding."
        )
    )


def _record_out_of_scope_finding(
    slug: str,
    project_root: Path,
    feature_path: Path,
    task: TaskContract,
    description: str,
    proposed_target: str,
) -> Path:
    """Materialize a finding under findings/FND-YYYY-MM-DD-NNN.yaml."""
    findings_dir = ensure_dir(feature_path / "findings")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = sorted(findings_dir.glob(f"FND-{today}-*.yaml"))
    next_idx = len(existing) + 1
    fid = f"FND-{today}-{next_idx:03d}"
    target = findings_dir / f"{fid}.yaml"
    payload = {
        "id": fid,
        "context": f"{task.task_id} implementation",
        "proposed-resolution": proposed_target,
        "scope": description,
        "status": "open",
        "discovered-at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    from engine.utils.yaml_io import write_yaml

    write_yaml(target, payload, atomic=True, backup=False)
    append_history(
        slug,
        project_root,
        {
            "event": "out-of-scope-finding-recorded",
            "task": task.task_id,
            "finding": fid,
            "path": str(target.relative_to(project_root)),
        },
    )
    return target


def _prompt_out_of_scope_paths(
    slug: str,
    project_root: Path,
    feature_path: Path,
    task: TaskContract,
) -> None:
    """Render the three-paths block for an out-of-scope event."""
    block = mentor_calmo.three_paths_block(
        gate_name="edição fora de allowed_files",
        what_failed=(
            "tentativa de editar arquivo não declarado em "
            f"tasks/{task.task_id}.yaml.allowed_files"
        ),
        where=str(task.path.relative_to(project_root)),
        why=[
            "hard-gate no-files-outside-allowed-files (workflow-config.yaml)",
            "discipline §1 — sem expansão silenciosa de escopo",
        ],
        paths=[
            {
                "label": "Atualizar Task Contract pra incluir o arquivo",
                "motive": "use quando a mudança REALMENTE pertence a esta task",
            },
            {
                "label": "Reverter — esquece a edição nesta task",
                "motive": "se foi tangente / refactor oportunista",
            },
            {
                "label": "Split em nova TASK — registro um Finding pendente",
                "motive": "se é trabalho legítimo mas pertence a outra unidade",
            },
        ],
    )
    renderer.write("")
    renderer.write(block)
    choice = question.ask_three_paths("out-of-scope-edit", [
        {"label": "Atualizar contract", "motive": ""},
        {"label": "Reverter edição", "motive": ""},
        {"label": "Split em nova task", "motive": ""},
    ])
    if choice == "a":
        path = question.ask_text(
            "Qual arquivo adicionar a allowed_files? (path relativo)",
        )
        renderer.write(
            f"Adicione manualmente '{path}' em "
            f"{task.path.relative_to(project_root)}.allowed_files "
            "e re-rode forge implement."
        )
        append_history(
            slug,
            project_root,
            {
                "event": "contract-expansion-requested",
                "task": task.task_id,
                "file": path,
            },
        )
    elif choice == "b":
        renderer.write("Edição revertida — siga com a task como está.")
        append_history(
            slug,
            project_root,
            {"event": "out-of-scope-reverted", "task": task.task_id},
        )
    else:
        description = question.ask_text(
            "Descreva o escopo do Finding (uma linha):"
        )
        target = _record_out_of_scope_finding(
            slug,
            project_root,
            feature_path,
            task,
            description=description,
            proposed_target=f"new TASK after {task.task_id}",
        )
        renderer.write(
            f"Finding gravado: {target.relative_to(project_root)}. "
            "Será revisado na próxima retrospectiva."
        )


# ── Slug elicitation ─────────────────────────────────────────────────────────


def _elicit_slug(argv_slug: Optional[str], project_root: Path) -> str:
    if argv_slug:
        if not _is_valid_slug(argv_slug):
            raise SystemExit(
                f"forge implement: slug '{argv_slug}' invalid. "
                "kebab-case lowercase, 2..50 chars, [a-z0-9-]."
            )
        return argv_slug

    return question.ask_text(
        "Qual feature implementar? (slug kebab-case)",
        validator=_is_valid_slug,
        validator_hint="kebab-case lowercase, 2..50 chars.",
    )


# ── Entry point ──────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:
    """`forge implement [feature-slug]` — execute one task with Plan Mode discipline."""
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge implement: {exc}\n")
        return 2

    argv_slug = argv[0] if argv else None
    try:
        slug = _elicit_slug(argv_slug, project_root)
    except PromptAbortedError:
        sys.stderr.write("\n— interrompido antes do slug, nada salvo.\n")
        return 130

    feature_path = _feature_path(project_root, slug)
    if not feature_path.is_dir():
        sys.stderr.write(
            f"forge implement: feature '{slug}' não existe em "
            f"{feature_path}. Rode `forge plan {slug}` primeiro.\n"
        )
        return 4

    is_ready, observed = _check_readiness(feature_path)
    if not is_ready:
        sys.stderr.write(
            f"forge implement: readiness='{observed}' — precisa estar 'ready'. "
            f"Rode `forge plan {slug}` e finalize Wave E.\n"
        )
        return 5

    tasks = _collect_tasks(feature_path)
    if not tasks:
        sys.stderr.write(
            f"forge implement: nenhum tasks/TASK-*.yaml em {feature_path}. "
            "Wave D do plano não foi concluída.\n"
        )
        return 6

    task = _pick_next_task(tasks)
    if task is None:
        renderer.write("")
        renderer.write(
            renderer.box(
                f"feature-forge · {slug} · todas as tasks fechadas",
                [
                    f"{len(tasks)} tasks · 0 pendentes",
                    "Próximo: forge evolve (se ainda não revisou propostas)",
                ],
                width=72,
            )
        )
        # Mark feature done if everything closed.
        state = read_l1_status(slug, project_root)
        if state and state.status != "done":
            state.status = "done"
            state.last_action_kind = "implement-completed"
            state.phase_lock = None
            write_l1_status(state, project_root)
            append_history(slug, project_root, {"event": "feature-done"})
        # Garante release do lock mesmo quando state era None ou já 'done'.
        release_phase_lock(slug, project_root)
        return 0

    # Acquire task-scoped phase lock.
    lock_id = task.task_id
    if not acquire_phase_lock(slug, project_root, lock_id):
        current = read_l1_status(slug, project_root)
        held = current.phase_lock if current else "?"
        sys.stderr.write(
            f"forge implement: '{slug}' phase-locked by '{held}'. "
            "Run `forge undo` to release, or wait.\n"
        )
        return 3

    # Cinematic header + auto-resume detection.
    state = read_l1_status(slug, project_root)
    if state and state.status == "implementing":
        renderer.write("")
        renderer.write(
            renderer.dim(
                f"Detectei implementação em andamento — continuando em {task.task_id}."
            )
        )
    else:
        if state is None:
            state = L1State(
                feature_slug=slug,
                status="implementing",
                last_action_at="",
                last_action_kind="implement-started",
                phase_lock=lock_id,
            )
        else:
            state.status = "implementing"
            state.last_action_kind = "implement-started"
        write_l1_status(state, project_root)

    renderer.write("")
    renderer.write(
        renderer.box(
            f"feature-forge · implement · {slug}",
            [
                "Plan Mode antes de tudo. Sem improviso.",
                f"Próxima task: {task.task_id}",
            ],
            width=72,
        )
    )

    try:
        _print_plan_mode(task, project_root)

        confirmed = question.confirm(
            "Topa esse plano? (sim segue pra Apply Mode)",
            default=False,
        )
        if not confirmed:
            renderer.write(
                renderer.dim(
                    "Plano não aprovado — saindo sem tocar arquivo. "
                    "Ajuste o contrato em " + str(task.path.relative_to(project_root))
                    + " e re-rode."
                )
            )
            append_history(
                slug,
                project_root,
                {"event": "plan-mode-rejected", "task": task.task_id},
            )
            # Plano rejeitado — libera lock pra próxima invocação não travar.
            release_phase_lock(slug, project_root)
            return 0

        append_history(
            slug,
            project_root,
            {
                "event": "plan-mode-approved",
                "task": task.task_id,
                "files-in-scope": len(task.allowed_files),
            },
        )

        _apply_mode_handoff(task, slug, project_root)

        # Bonus interactive offer — surface the out-of-scope flow on demand,
        # so users see how the gate fires before they trip it.
        if question.confirm(
            "Quer ver o fluxo de out-of-scope agora (registrar Finding)?",
            default=False,
        ):
            _prompt_out_of_scope_paths(slug, project_root, feature_path, task)

    except PromptAbortedError:
        # Pause — keep state, release lock so other commands can run.
        release_phase_lock(slug, project_root)
        append_history(
            slug,
            project_root,
            {"event": "implement-paused", "task": task.task_id},
        )
        renderer.write("")
        renderer.write(
            mentor_calmo.pause_message(
                slug=slug, resume_command=f"forge implement {slug}"
            )
        )
        return 130

    # Apply Mode handoff entregue — libera lock antes do retorno (próxima
    # invocação `forge implement` precisa adquirir lock pra nova TASK).
    release_phase_lock(slug, project_root)
    return 0


__all__ = ["run"]
