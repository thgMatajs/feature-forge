"""`forge implement` — execution conductor (Plan Mode → Apply → next task).

IMPLEMENT-HANDOFF (BY-DESIGN, Decisão 22): `forge implement` ORQUESTRA o
lifecycle de implementação — NÃO gera código. A autoria do código é handoff
explícito pro host (Claude Code / opencode), que escreve contra o Task Contract
que o forge surfa. Isso é o exec model canônico (engine emite intent + gates;
o host implementa), não um stub quebrado a completar. O engine nunca importa
nem invoca outra skill pra gerar código (Decisão 22 — zero runtime dep).

Single Task Contract per invocation. Walks the user/host through:

    1. Resolve feature slug + state guard (readiness must be 'ready').
    2. Pick next task via task-breakdown DAG topo-sort + status filter.
    3. Plan Mode: surface contract + bdd_scenarios_covered + allowed_files
       + gates + validations. Block on user 'sim'.
    4. Apply Mode: handoff de autoria pro host — o forge surfa o contrato e
       o host escreve o código contra ele (não é stub a preencher; é o
       exec model). Edits fora de escopo viram findings/FND-*.yaml via o
       three-paths block.
    5. Verify + Commit são user/host-driven — emite hand-off copy que aponta
       pra `forge verify` + uma mensagem de commit convencional.

Exit codes:
    0    task acknowledged / parked between tasks
    130  user pause
    other  hard gate violation
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.memory.l1 import (
    L1State,
    append_history,
    blocking_deps,
    current_phase_lock,
    is_blocked,
    phase_lock_held,
    read_l1_status,
    release_phase_lock,
    write_l1_status,
)
from engine.persona import mentor_calmo
from engine.ui import question, renderer
from engine.ui.exit_codes import (
    ERR_BLOCKED_EXTERNAL,
    ERR_FEATURE_MISSING,
    ERR_LOCKED,
    ERR_NOT_READY,
    ERR_PROJECT_NOT_FOUND,
    ERR_WAVE_INCOMPLETE,
    fail_with_tag,
)
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    active_config_path,
    claude_dir,
    ensure_dir,
    feature_dir,
    feature_path as _feature_path,
    find_project_root,
    forge_state_dir,
)
from engine.utils.yaml_io import read_yaml, read_yaml_or_default, write_yaml
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    load_yaml_checkpoint as _load_yaml_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso
from engine.integrations.mem import mem_context_hint

_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,48}[a-z0-9]$")
_TASK_ID_PATTERN = re.compile(r"^TASK-(\d{4})$")


# ── Checkpoint (DRIFT-1 W2.T3b — intent-resume, outcome C) ───────────────────
#
# Per the T3a audit (.planning/drift-1/checkpoint-audit.json,
# action="add-new", reuse_path="init-pattern"), implement ganha
# checkpoint pra cobrir os 7 callsites interativos: ask_text de slug,
# confirm de plan-mode, confirm bonus de out-of-scope, ask_three_paths
# em out-of-scope-edit e qa.auto-run, ask_text de finding description e
# allowed_files-path. Mirrors ``_InitCheckpoint`` (engine/init.py:100-108)
# — outcome C, sem import de ``engine.qa.checkpoint`` (Decision 22).
#
# Refs:
#   - docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
#   - engine/init.py:100-108 (canonical template)


@dataclass
class _ImplementCheckpoint:
    """State serialized before each ``question.ask*`` call in ``implement.run``.

    Carries ``feature_slug`` + ``task_id`` (quando ja resolvidos pelo
    fluxo) pra que o host saiba em que feature/task o pause aconteceu.
    Prompts antes da resolucao do slug recebem ``feature_slug=None``.
    """

    step: str
    at: str
    project_root: str
    intent_id: str | None = None
    feature_slug: str | None = None
    task_id: str | None = None


def _implement_checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / ".implement-checkpoint.yaml"


# Os helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` —
# consolidação dos 30 duplicates apontada pelos findings #5 e #21 do master
# review do PR #11. Os nomes ``_save_implement_checkpoint`` etc. permanecem
# como API privada do módulo para preservar os contracts dos testes em
# ``tests/unit/test_engine_implement_resume.py`` (Mandamento #2 — verde).
# L-03 (PR #remediation): ``_utc_now_iso_*`` shims removidos; callers
# usam ``utc_now_iso`` direto de ``engine.utils.iso``.


def _save_implement_checkpoint(cp: _ImplementCheckpoint) -> None:
    """Persist the implement checkpoint atomically."""
    _save_yaml_checkpoint_io(
        _implement_checkpoint_path(Path(cp.project_root)),
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "intent-id": cp.intent_id,
            "feature-slug": cp.feature_slug,
            "task-id": cp.task_id,
        },
    )


def _load_implement_checkpoint(project_root: Path) -> dict[str, Any] | None:
    """Read the implement checkpoint, returning ``None`` when absent."""
    return _load_yaml_checkpoint_io(_implement_checkpoint_path(project_root))


def _clear_implement_checkpoint(project_root: Path) -> None:
    """Remove the checkpoint — best-effort; silent on OSError (idempotent)."""
    _clear_checkpoint_io(_implement_checkpoint_path(project_root))


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
    # Discipline §9 — external dependencies. List of dicts shaped like:
    #   {"ticket": str, "integration": str, "description": str,
    #    "blocking": bool, "declared-at": str|None, "resolved-at": str|None}
    # Empty list when the task carries no external deps.
    external_deps: list[dict[str, Any]] = field(default_factory=list)


def _is_valid_slug(value: str) -> bool:
    return bool(_SLUG_PATTERN.match(value))


# ── Readiness gate ───────────────────────────────────────────────────────────


def _readiness_from_handoff(handoff: Path) -> str | None:
    if not handoff.exists():
        return None
    try:
        data = json.loads(handoff.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
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


def _readiness_from_review(review: Path) -> str | None:
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


_READY_VERDICTS = {"ready", "ready-with-blocks"}


def _check_readiness(feature_path: Path) -> tuple[bool, str]:
    """Return (is_ready, observed_status).

    Both `ready` and `ready-with-blocks` (discipline §9) unlock implement.
    `ready-with-blocks` means at least one task has an unresolved external
    dep — execution-conductor handles the per-task refusal downstream.
    """
    handoff = feature_path / "plan-feature-handoff.json"
    review = feature_path / "implementation-readiness-review.md"
    status = _readiness_from_handoff(handoff) or _readiness_from_review(review) or "unknown"
    return status in _READY_VERDICTS, status


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

    # Discipline §9 — depends_on_external. Accept both snake/kebab variants.
    ext_deps = (
        raw.get("depends_on_external") or raw.get("depends-on-external") or []
    )
    if not isinstance(ext_deps, list):
        ext_deps = []
    normalized_ext: list[dict[str, Any]] = []
    for entry in ext_deps:
        if not isinstance(entry, dict):
            continue
        normalized_ext.append(
            {
                "ticket": str(entry.get("ticket") or ""),
                "integration": str(entry.get("integration") or "manual"),
                "description": str(entry.get("description") or ""),
                "blocking": bool(entry.get("blocking", True)),
                "declared-at": entry.get("declared-at")
                or entry.get("declared_at"),
                "resolved-at": entry.get("resolved-at")
                or entry.get("resolved_at"),
            }
        )

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
        external_deps=normalized_ext,
    )


def _task_blocking_deps(task: TaskContract) -> list[dict[str, Any]]:
    """Return unresolved blocking external deps for this task (or [])."""
    return [
        d
        for d in task.external_deps
        if d.get("blocking", True) and not d.get("resolved-at")
    ]


def _collect_tasks(feature_path: Path) -> list[TaskContract]:
    tasks_dir = feature_path / "tasks"
    if not tasks_dir.is_dir():
        return []
    files = sorted(p for p in tasks_dir.glob("TASK-*.yaml") if p.is_file())
    return [_load_task_contract(p) for p in files]


class TaskGraphError(RuntimeError):
    """A-008 (master review PR #15): domain exception para erros no DAG de tasks.

    Substitui `SystemExit` em `_topo_sort` — `SystemExit` é `BaseException`,
    não pega em `except Exception`, e qualquer chamador defensivo (tests,
    hooks, embedded use) perdia mensagem ou terminava abruptamente. Validação
    de DAG não é shutdown; o CLI `run()` é quem mapeia esta exceção pro
    exit code não-zero do entry-point.
    """


def _topo_sort(tasks: list[TaskContract]) -> list[TaskContract]:
    """Stable topological sort by `dependencies`. Cycles raise TaskGraphError."""
    by_id = {t.task_id: t for t in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()
    order: list[TaskContract] = []

    def _visit(node_id: str, stack: list[str]) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            chain = " → ".join(stack + [node_id])
            raise TaskGraphError(
                f"forge implement: dependency cycle detected ({chain})"
            )
        if node_id not in by_id:
            # M-02: dep apontando pra task inexistente é erro de contrato,
            # não warning. Continuar trataria estado inválido como válido
            # e a feature avançaria com DAG furado.
            raise TaskGraphError(
                f"forge implement: task '{node_id}' declared in "
                "dependencies does not exist. Fix the dependency reference."
            )
        visiting.add(node_id)
        for dep in by_id[node_id].dependencies:
            _visit(dep, stack + [node_id])
        visiting.discard(node_id)
        visited.add(node_id)
        order.append(by_id[node_id])

    for task in tasks:
        _visit(task.task_id, [])
    return order


def _pick_next_task(
    tasks: list[TaskContract], *, skip_blocked: bool = False
) -> TaskContract | None:
    """Pick the next runnable task in topo order.

    When `skip_blocked=True`, tasks with unresolved blocking external deps
    are skipped (discipline §9). Default is False so the caller can decide
    whether to refuse + offer 3-caminhos or auto-skip.
    """
    done = {t.task_id for t in tasks if t.status == "done"}
    sorted_tasks = _topo_sort(tasks)
    for task in sorted_tasks:
        if task.status == "done":
            continue
        unresolved = [d for d in task.dependencies if d not in done]
        if unresolved:
            continue
        if skip_blocked and _task_blocking_deps(task):
            continue
        return task
    return None


def _print_blocked_refusal(
    task: TaskContract,
    alt_task: TaskContract | None,
) -> None:
    """Render the canonical 3-caminhos block for a task blocked on external deps.

    Discipline §9 — the user gets exactly three legitimate paths:
      A) Mark the dep resolved via `forge reconfigure` (when ticket actually closed)
      B) Pick another task without external blocks (when one exists)
      C) Pause the feature entirely (deferred)
    """
    blocking = _task_blocking_deps(task)

    renderer.write("")
    renderer.write(
        renderer.bold(
            f"🛑 {task.task_id} bloqueada por dependência externa"
        )
    )
    renderer.write("")
    renderer.write("O que falhou:")
    for dep in blocking:
        ticket = dep.get("ticket") or "?"
        integration = dep.get("integration") or "manual"
        descr = dep.get("description") or "(sem descrição)"
        renderer.write(f"  · {ticket} ({integration}) — {descr}")
    renderer.write("")
    renderer.write("Onde:")
    renderer.write(f"  {task.path.name}.depends_on_external")
    renderer.write("")
    renderer.write("Por que importa:")
    renderer.write(
        "  · Hard-gate readiness-must-be-ready exige dep externa resolvida"
    )
    renderer.write(
        "  · Implementar contra endpoint imaginário = invented behavior"
    )
    renderer.write(
        "  · Tempo perdido refatorando quando o ticket real fechar"
    )
    renderer.write("")
    renderer.write("Três caminhos:")
    renderer.write("")
    renderer.write(
        "  1) Marcar dep externa como resolvida agora\n"
        "     `forge reconfigure` → external-deps → marcar como resolvida"
    )
    if alt_task is not None:
        renderer.write("")
        renderer.write(
            f"  2) Pegar {alt_task.task_id} (deps satisfeitas, zero ext.)\n"
            f"     {alt_task.description or '<sem descrição>'}"
        )
    else:
        renderer.write("")
        renderer.write(
            "  2) (sem outras tasks runáveis no DAG)\n"
            "     todas as alternativas têm deps internas ou externas pendentes"
        )
    renderer.write("")
    renderer.write(
        "  3) Pausar a feature inteira\n"
        "     state → deferred (volta quando o ticket fechar)"
    )
    renderer.write("")
    renderer.write(renderer.dim("Sem auto-fix aqui — escolha humana."))


# ── Plan Mode reveal ─────────────────────────────────────────────────────────


def _print_plan_mode(task: TaskContract, project_root: Path) -> None:
    # W-ROUTE 6c: lê memória relevante antes de renderizar o Plan Mode.
    # O resultado alimenta o context-pack que o host vê na tela de confirmação.
    # Degrade soft: mem ausente → hint é None → bloco omitido silenciosamente.
    _hint = mem_context_hint(
        project_root, task.description or task.task_id, limit=5
    )
    renderer.write("")
    renderer.write(renderer.bold(f"📋 Plan Mode · {task.task_id}"))
    if _hint is not None:
        renderer.write("")
        renderer.write(renderer.dim(_hint))
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


# ── CC gate per-task hook ────────────────────────────────────────────────────


def _cc_bypass_log_path(project_root: Path) -> Path:
    """Audit trail location for ``NO_CC_GATE=1`` bypass invocations.

    Task 0.8 (v1.3 pilot-ready): state file vive em
    ``.claude/forge/state/cc-gate-bypass.jsonl`` (sub-namespace spec §2).
    """
    return forge_state_dir(project_root) / "cc-gate-bypass.jsonl"


def _run_cc_gate(project_root: Path) -> dict[str, Any]:
    """Invoke ``check_cyclomatic_complexity.validate`` as an in-process call.

    Returns the validator result dict augmented with ``blocking: bool``:

    - ``blocking=True``  → commit must NOT proceed; 3-paths block surfaced.
    - ``blocking=False`` → pass / warn / bypass — handoff continues.

    Bypass: ``NO_CC_GATE=1`` env var short-circuits the validator and
    appends one record to ``.claude/forge/state/cc-gate-bypass.jsonl`` for audit.
    Override-justify (``CC-OVERRIDE: …``) in the commit body is handled
    *inside* the validator — pass-through here.
    """
    if os.environ.get("NO_CC_GATE", "").strip().lower() in {"1", "true", "yes"}:
        log_path = _cc_bypass_log_path(project_root)
        try:
            ensure_dir(log_path.parent)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {"at": ts, "reason": "NO_CC_GATE env var set"},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError:
            # Audit best-effort — never let logging block the bypass.
            pass
        return {
            "status": "warn",
            "message": "NO_CC_GATE=1 — gate bypassed",
            "blocking": False,
        }

    # Lazy import — avoids circular deps when engine boots without validators on path.
    try:
        from validators import check_cyclomatic_complexity as cc_validator
    except ImportError:
        return {
            "status": "warn",
            "message": "cc-gate validator unavailable (import failed)",
            "blocking": False,
        }

    try:
        result = cc_validator.validate(project_root)
    except Exception as exc:  # noqa: BLE001 — broad catch: defensive at validator-dispatch boundary; validator crashes warn  # pragma: no cover
        return {
            "status": "warn",
            "message": f"cc-gate validator crashed: {exc}",
            "blocking": False,
        }

    if not isinstance(result, dict):
        return {
            "status": "warn",
            "message": "cc-gate validator returned non-dict result",
            "blocking": False,
        }

    result["blocking"] = result.get("status") == "fail"
    return result


def _render_cc_gate_block(result: dict[str, Any]) -> None:
    """Render the gate's 3-paths block when blocking.

    Prefers the canonical `render` field (`format_three_paths_message` output)
    when available — it carries the load-bearing UX contract from spec §4
    and disciplines §1 (literal header `🛑 Cyclomatic Complexity gate`,
    sections "O que falhou:", "Onde:", "Por que importa:", "Três caminhos
    pra resolver:"). Falls back to a per-path render when `render` is not
    present, keeping backward compatibility with non-CC consumers.
    """
    renderer.write("")
    canonical = result.get("render")
    if isinstance(canonical, str) and canonical.strip():
        # Canonical render already includes header + sections + footer.
        for line in canonical.splitlines():
            renderer.write(line)
        # Surface malformed-override warnings (H4) so the user sees why
        # their attempted CC-OVERRIDE didn't silence the fail.
        warnings = result.get("warnings") or []
        if warnings:
            renderer.write("")
            renderer.write(renderer.dim("Avisos:"))
            for w in warnings:
                renderer.write(renderer.dim(f"  · {w}"))
        return

    # Fallback render — kept for results that lack the canonical block.
    renderer.write(renderer.bold(result.get("message") or "cc-gate hard fail"))
    renderer.write("")
    for p in result.get("paths") or []:
        label = p.get("label") or p.get("kind") or "?"
        motive = p.get("motive") or ""
        renderer.write(f"  · {label}")
        if motive:
            renderer.write(f"      {motive}")
    renderer.write("")
    renderer.write(renderer.dim("Sem auto-fix aqui — escolha humana."))


# ── Secrets gate per-task hook ───────────────────────────────────────────────


def _secrets_bypass_log_path(project_root: Path) -> Path:
    """Trilha de auditoria para invocações ``NO_SECRETS_GATE=1``.

    Paralelo de ``_cc_bypass_log_path`` — cada bypass escreve uma linha
    JSONL para auditoria via ``git log`` / scripts off-band. Path
    consistente com o pattern do CC gate (mesma pasta
    ``.claude/forge/state/``).

    Task 0.8 (v1.3 pilot-ready): migrado pra ``forge_state_dir`` helper —
    state vive sob o sub-namespace ``.claude/forge/`` (spec §2).
    """
    return forge_state_dir(project_root) / "secrets-gate-bypass.jsonl"


def _run_secrets_gate(project_root: Path) -> dict[str, Any]:
    """Invoca ``validators.check_secrets.validate`` com stage="per_task".

    Per-task hook usa gitleaks (regex, ~100ms — sem network roundtrip);
    a cascade do ``forge verify`` é quem chama com stage="cascade"
    (trufflehog --only-verified). Ver spec §2 brainstorm pra rationale
    do split per-stage.

    Returns:
        Result dict augmentado com ``blocking: bool``:

        - ``blocking=True``  → commit NÃO deve prosseguir; render 3-paths surface.
        - ``blocking=False`` → pass / warn / bypass — handoff continua.

    Bypass: ``NO_SECRETS_GATE=1`` env var faz short-circuit do validator e
    appenda um registro em ``.claude/forge/state/secrets-gate-bypass.jsonl`` pra
    auditoria. Override-justify (``SECRETS-OVERRIDE: …``) no commit body é
    tratado *dentro* do validator — pass-through aqui.

    Modo defensivo (mentor calmo, sem rage-fail): import-fail, exceção do
    validator, ou non-dict result → ``status=warn`` + ``blocking=False``.
    Engine boot é resiliente — secrets-gate ausente NÃO bloqueia
    ``forge implement``, só perde cobertura (warn surface ao usuário).
    """
    if os.environ.get("NO_SECRETS_GATE", "").strip().lower() in {"1", "true", "yes"}:
        log_path = _secrets_bypass_log_path(project_root)
        try:
            ensure_dir(log_path.parent)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {"at": ts, "reason": "NO_SECRETS_GATE env var set"},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError:
            # Audit best-effort — never let logging block the bypass.
            pass
        return {
            "status": "warn",
            "message": "NO_SECRETS_GATE=1 — gate bypassed",
            "blocking": False,
        }

    # Lazy import — engine boot continua mesmo sem validators no path.
    try:
        from validators import check_secrets as secrets_validator
    except ImportError:
        return {
            "status": "warn",
            "message": "secrets-gate validator unavailable (import failed)",
            "blocking": False,
        }

    try:
        result = secrets_validator.validate(project_root, stage="per_task")
    except Exception as exc:  # noqa: BLE001 — broad catch: defensive at validator-dispatch boundary; validator crashes warn  # pragma: no cover
        return {
            "status": "warn",
            "message": f"secrets-gate validator crashed: {exc}",
            "blocking": False,
        }

    if not isinstance(result, dict):
        return {
            "status": "warn",
            "message": "secrets-gate validator returned non-dict result",
            "blocking": False,
        }

    result["blocking"] = result.get("status") == "fail"
    return result


def _render_secrets_gate_block(result: dict[str, Any]) -> None:
    """Renderiza o bloco 3-paths do secrets-gate quando blocking.

    Paralelo de ``_render_cc_gate_block`` — prefere o campo canonical
    ``render`` (saída de ``_render_secrets_three_paths``) quando presente.
    Esse render carrega o contrato UX literal do spec §3 + disciplina §1
    (header ``🛑 Check Secrets gate`` + seções "O que falhou:", "Onde:",
    "Por que importa:", "Três caminhos pra resolver:"). Fallback per-path
    cobre results legacy que não trazem o canonical.
    """
    renderer.write("")
    canonical = result.get("render")
    if isinstance(canonical, str) and canonical.strip():
        for line in canonical.splitlines():
            renderer.write(line)
        warnings = result.get("warnings") or []
        if warnings:
            renderer.write("")
            renderer.write(renderer.dim("Avisos:"))
            for w in warnings:
                renderer.write(renderer.dim(f"  · {w}"))
        return

    # Fallback render — para results sem o canonical block.
    renderer.write(renderer.bold(result.get("message") or "secrets-gate hard fail"))
    renderer.write("")
    for p in result.get("paths") or []:
        label = p.get("label") or p.get("kind") or "?"
        motive = p.get("motive") or ""
        renderer.write(f"  · {label}")
        if motive:
            renderer.write(f"      {motive}")
    renderer.write("")
    renderer.write(renderer.dim("Sem auto-fix aqui — escolha humana."))


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

    cc_result = _run_cc_gate(project_root)
    if cc_result.get("blocking"):
        _render_cc_gate_block(cc_result)
        renderer.write("")
        renderer.write(
            "Resolva o gate antes de commitar. Re-rode `forge implement` "
            "depois de refatorar / split / adicionar CC-OVERRIDE no commit body."
        )
        return  # do not emit commit instructions while gate is blocking
    if cc_result.get("status") == "warn":
        msg = cc_result.get("message", "")
        if msg:
            renderer.write(renderer.dim(f"cc-gate: {msg}"))
            renderer.write("")

    # Gates agrupados (anti-pattern de gate isolado) — secrets roda
    # IMEDIATAMENTE após CC, mesma posição relativa que tem na cascade do
    # forge verify (Sub-Task 5A: check_secrets segue check_cyclomatic_complexity
    # em _DEFAULT_VALIDATORS).
    secrets_result = _run_secrets_gate(project_root)
    if secrets_result.get("blocking"):
        _render_secrets_gate_block(secrets_result)
        renderer.write("")
        renderer.write(
            "Resolva o gate antes de commitar. Re-rode `forge implement` "
            "depois de remover/rotacionar ou adicionar SECRETS-OVERRIDE "
            "no commit body."
        )
        return  # do not emit commit instructions while gate is blocking
    if secrets_result.get("status") == "warn":
        msg = secrets_result.get("message", "")
        if msg:
            renderer.write(renderer.dim(f"secrets-gate: {msg}"))
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


# ── QA auto-run hook (Phase 6 pre-retrospective, §12.1) ────────────────────


def _maybe_run_qa_pre_retrospective(
    feature_slug: str,
    project_root: Path,
) -> None:
    """Dispara `forge qa` antes do retrospective quando opt-in está ativo.

    Spec §12.1 — workflow-config `qa.auto-run-on-feature-done: true`
    aciona este hook na transição feature → done (Phase 6 do execution
    conductor). Verdict NÃO bloqueia (§12.2): findings entram como
    insumo, decisão fica com o user via `forge evolve`.

    Args:
        feature_slug: slug da feature recém-concluída (passado pra
            `engine.qa.run_qa` como scope=feature target).
        project_root: raiz do projeto consumidor.

    Behavior:
        - Lê `workflow-config.yaml` → `qa:`
        - Se `qa.enabled: false` OR `qa.auto-run-on-feature-done: false`,
          retorna silenciosamente (no-op é o comportamento esperado;
          default config tem auto-run desligado).
        - Caso ambos true: 3-caminhos (run / skip / disable). Verdict
          é informativo — não levanta SystemExit nem propaga retorno.
        - Falhas ao rodar qa são logadas em history mas não bloqueiam
          o fluxo da feature-done.

    Reuso (mandamento #3):
        - `ask_three_paths` + `three_paths_block` (engine.persona + ui)
        - `append_history` (engine.memory.l1) — pattern já usado em
          out-of-scope finding flow acima.
        - `run_qa` (engine.qa) — import lazy pra evitar circular dep
          (engine.qa importa nada de implement, mas chain de imports
          do package qa puxa engine.cards/graph que indiretamente toca
          este módulo via forge/state/lifecycle; lazy import é defesa idiomática).
    """
    cfg = read_yaml_or_default(active_config_path(project_root), {})
    if not isinstance(cfg, dict):
        return
    qa_cfg = cfg.get("qa") or {}
    if not isinstance(qa_cfg, dict):
        return
    if not qa_cfg.get("enabled", True):
        return
    if not qa_cfg.get("auto-run-on-feature-done", False):
        return

    # 3-caminhos antes do dispatch — discipline §1, pattern já usado em
    # _prompt_out_of_scope_paths acima. Bloco visual + ask_three_paths
    # casados em par canônico.
    block = mentor_calmo.three_paths_block(
        gate_name="qa.auto-run-on-feature-done",
        what_failed=(
            "qa.auto-run-on-feature-done está ativo e a feature acaba "
            "de fechar — rodar forge qa antes do retrospective?"
        ),
        where=str(active_config_path(project_root).relative_to(project_root)),
        why=[
            "verdict QA é insumo pro retrospective (não bloqueia — §12.2)",
            "contexto fresco vale mais barato agora que depois",
        ],
        paths=[
            {
                "label": "Rodar agora (recomendado — contexto fresco)",
                "motive": "feature acabou; findings entram no retrospective",
            },
            {
                "label": "Pular nesta feature (registra em history)",
                "motive": "decisão consciente — auditoria preservada",
            },
            {
                "label": "Desativar auto-run permanentemente",
                "motive": "toggle em workflow-config qa.auto-run-on-feature-done",
            },
        ],
    )
    renderer.write("")
    renderer.write(block)

    try:
        choice = question.ask_three_paths(
            "qa.auto-run-on-feature-done",
            [
                {"label": "Rodar agora", "motive": ""},
                {"label": "Pular nesta feature", "motive": ""},
                {"label": "Desativar auto-run", "motive": ""},
            ],
        )
    except PromptAbortedError:
        # Pausa pelo user — registra como skipped e segue. Mandamento #4
        # (scope contido): hook não pode aumentar o blast radius da
        # interrupção do user.
        append_history(
            feature_slug,
            project_root,
            {"event": "qa-auto-run-skipped", "reason": "user-pause"},
        )
        return

    if choice == "a":
        from engine.qa import run_qa  # noqa: PLC0415 — lazy

        try:
            exit_code = run_qa(
                feature_slug,
                project_root=project_root,
                workflow_config=cfg,
            )
        except Exception as exc:  # noqa: BLE001 — broad catch: defensive at qa auto-run cross-module boundary; verdict não bloqueia
            renderer.write(
                renderer.colored(
                    f"qa auto-run falhou ({type(exc).__name__}: {exc}); "
                    "seguindo pro retrospective sem findings.",
                    "yellow",
                )
            )
            append_history(
                feature_slug,
                project_root,
                {
                    "event": "qa-auto-run-error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            return
        append_history(
            feature_slug,
            project_root,
            {"event": "qa-auto-run-completed", "exit_code": exit_code},
        )
    elif choice == "b":
        append_history(
            feature_slug,
            project_root,
            {"event": "qa-auto-run-skipped", "reason": "user-choice"},
        )
        renderer.write(renderer.dim("ok, pulando qa nesta feature."))
    else:  # "c" — disable permanently
        _toggle_qa_auto_run_off(project_root)
        append_history(
            feature_slug,
            project_root,
            {"event": "qa-auto-run-disabled-by-user"},
        )
        renderer.write(
            renderer.dim(
                "auto-run desativado em workflow-config (qa.auto-run-on-feature-done=false)."
            )
        )


def _toggle_qa_auto_run_off(project_root: Path) -> None:
    """Persiste `qa.auto-run-on-feature-done: false` em workflow-config.

    Helper isolado pra facilitar mock em testes (Wave 8.4) sem precisar
    interceptar file I/O do write_yaml. Idempotente — se já estiver
    false, escreve mesmo assim (custo desprezível, evita branch dupla).
    """
    from engine.utils.yaml_io import write_yaml  # noqa: PLC0415 — lazy

    cfg_path = active_config_path(project_root)
    cfg = read_yaml_or_default(cfg_path, {})
    if not isinstance(cfg, dict):
        cfg = {}
    qa_cfg = cfg.get("qa") or {}
    if not isinstance(qa_cfg, dict):
        qa_cfg = {}
    qa_cfg["auto-run-on-feature-done"] = False
    cfg["qa"] = qa_cfg
    write_yaml(cfg_path, cfg, atomic=True)


# ── Slug elicitation ─────────────────────────────────────────────────────────


def _elicit_slug(argv_slug: str | None, project_root: Path) -> str:
    if argv_slug:
        if not _is_valid_slug(argv_slug):
            raise SystemExit(
                f"forge implement: slug '{argv_slug}' invalid. "
                "kebab-case lowercase, 2..50 chars, [a-z0-9-]."
            )
        return argv_slug

    # DRIFT-1 W2.T3b — persist checkpoint com intent-id determinado da
    # pergunta de slug ANTES de invocar ``question.ask_text``. On exit-2 +
    # re-invoke, ``question.ask_text`` finds the matching forge-response
    # and returns the value without re-prompting. Outcome C — per-subcommand
    # dataclass, no import from ``engine.qa.checkpoint``.
    _save_implement_checkpoint(
        _ImplementCheckpoint(
            step="step-elicit-slug",
            at=utc_now_iso(),
            project_root=str(project_root),
            intent_id=question.stable_intent_id(
                "ask_text",
                "Qual feature implementar? (slug kebab-case)",
                None,
                extra={
                    "default": None,
                    "min-selected": None,
                    "validator-hint": "kebab-case lowercase, 2..50 chars.",
                },
            ),
            feature_slug=None,
        )
    )
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
        return fail_with_tag(ERR_PROJECT_NOT_FOUND)

    argv_slug = argv[0] if argv else None
    try:
        slug = _elicit_slug(argv_slug, project_root)
    except PromptAbortedError:
        sys.stderr.write("\n— interrompido antes do slug, nada salvo.\n")
        return 130

    # DRIFT-1 W2.T3b — agora que temos slug, atualiza checkpoint com
    # feature_slug; demais prompts deste handler (plan-mode confirm,
    # out-of-scope flow, qa-auto-run) herdam intent-resume via
    # question.ask*. Outcome C — sem import de engine.qa.checkpoint.
    _save_implement_checkpoint(
        _ImplementCheckpoint(
            step="step-post-slug",
            at=utc_now_iso(),
            project_root=str(project_root),
            intent_id=None,
            feature_slug=slug,
        )
    )

    feature_path = _feature_path(project_root, slug)
    if not feature_path.is_dir():
        sys.stderr.write(
            f"forge implement: feature '{slug}' não existe em "
            f"{feature_path}. Rode `forge plan {slug}` primeiro.\n"
        )
        _clear_implement_checkpoint(project_root)
        return fail_with_tag(ERR_FEATURE_MISSING)

    is_ready, observed = _check_readiness(feature_path)
    if not is_ready:
        sys.stderr.write(
            f"forge implement: readiness='{observed}' — precisa estar 'ready'. "
            f"Rode `forge plan {slug}` e finalize Wave E.\n"
        )
        _clear_implement_checkpoint(project_root)
        return fail_with_tag(ERR_NOT_READY)

    tasks = _collect_tasks(feature_path)
    if not tasks:
        sys.stderr.write(
            f"forge implement: nenhum tasks/TASK-*.yaml em {feature_path}. "
            "Wave D do plano não foi concluída.\n"
        )
        _clear_implement_checkpoint(project_root)
        return fail_with_tag(ERR_WAVE_INCOMPLETE)

    # Discipline §9 — recompute feature blocked state at startup.
    # When state was blocked-on-external from a previous session and the user
    # marked the ticket as resolved via `forge reconfigure`, this flip restores
    # implementing automatically. The reverse (implementing → blocked) happens
    # below on the first refusal.
    startup_state = read_l1_status(slug, project_root)
    if startup_state and startup_state.status == "blocked-on-external":
        if not is_blocked(slug, project_root):
            startup_state.status = "implementing"
            startup_state.last_action_kind = "blocked-external-cleared"
            write_l1_status(startup_state, project_root)
            append_history(
                slug,
                project_root,
                {"event": "blocked-external-cleared"},
            )

    try:
        task = _pick_next_task(tasks)
    except TaskGraphError as exc:
        # A-008 (master review PR #15): map domain exception to CLI exit code.
        sys.stderr.write(f"{exc}\n")
        return 1
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
            # §12.1 — pre-retrospective hook. Dispara forge qa quando opt-in
            # ativo. Verdict NÃO bloqueia (§12.2): findings entram como
            # insumo pro retrospective (futuro), sem alterar a transição
            # done aqui. Hook é no-op default — auto-run-on-feature-done
            # tem default false.
            _maybe_run_qa_pre_retrospective(slug, project_root)

            state.status = "done"
            state.last_action_kind = "implement-completed"
            state.phase_lock = None
            # Gap 9 (W-002) — stamp shipped-at on the done transition so
            # extension features can render `Parent shipped: <ISO>` from the
            # parent's status.json. Lives in `raw` (additive metadata; not a
            # canonical L1State field) so write_l1_status preserves it via
            # the raw round-trip. Idempotent: only set when absent — re-runs
            # of a done feature (rare; defensive) don't clobber the original
            # ship timestamp.
            if isinstance(state.raw, dict) and not state.raw.get("shipped-at"):
                state.raw["shipped-at"] = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
            write_l1_status(state, project_root)
            append_history(slug, project_root, {"event": "feature-done"})
        # Garante release do lock mesmo quando state era None ou já 'done'.
        release_phase_lock(slug, project_root)
        # DRIFT-1 W2.T3b — clear intent-resume checkpoint on clean completion.
        _clear_implement_checkpoint(project_root)
        return 0

    # Discipline §9 — refuse to start a task with unresolved blocking deps.
    # Flip feature state to blocked-on-external on FIRST refusal of a session
    # (idempotent on subsequent calls). Offer 3-caminhos block.
    task_blockers = _task_blocking_deps(task)
    if task_blockers:
        # Find an alternative task (deps satisfied AND zero blocking external).
        try:
            alternative = _pick_next_task(tasks, skip_blocked=True)
        except TaskGraphError as exc:
            sys.stderr.write(f"{exc}\n")
            return 1
        # Skip the same task if topo handed us the blocked one again.
        if alternative is not None and alternative.task_id == task.task_id:
            alternative = None

        # Flip feature state only when not already blocked.
        st = read_l1_status(slug, project_root)
        if st and st.status != "blocked-on-external":
            previous_status = st.status
            st.status = "blocked-on-external"
            st.last_action_kind = "blocked-on-external-detected"
            write_l1_status(st, project_root)
            append_history(
                slug,
                project_root,
                {
                    "event": "blocked-on-external-detected",
                    "task": task.task_id,
                    "tickets": [d.get("ticket") for d in task_blockers],
                    "previous-status": previous_status,
                },
            )
        elif st is None:
            new = L1State(
                feature_slug=slug,
                status="blocked-on-external",
                last_action_at="",
                last_action_kind="blocked-on-external-detected",
            )
            write_l1_status(new, project_root)
            append_history(
                slug,
                project_root,
                {
                    "event": "blocked-on-external-detected",
                    "task": task.task_id,
                    "tickets": [d.get("ticket") for d in task_blockers],
                },
            )

        _print_blocked_refusal(task, alternative)
        # A3 fix: do NOT unconditionally release here. This branch fires
        # BEFORE we acquire the phase lock for `task.task_id` (the
        # `with phase_lock_held(...)` below). An unconditional release would
        # strip a stale lock from ANOTHER flow (e.g. `forge plan` mid-write)
        # without authorization — violating the single-writer invariant.
        # If a stale lock genuinely exists from this aborted flow, `forge
        # undo` is the canonical recovery path.
        # DRIFT-1 W2.T3b — clear intent-resume checkpoint on hard-gate return.
        _clear_implement_checkpoint(project_root)
        return fail_with_tag(ERR_BLOCKED_EXTERNAL)

    # Acquire task-scoped phase lock via context manager (MD-03 refactor).
    # The CM owns acquire + release bookkeeping — every exit path (normal
    # return, PromptAbortedError, unexpected exception) flows through
    # __exit__ which releases iff we won the race. No more lock_released
    # flag to forget to flip when a new return is added inside the block.
    lock_id = task.task_id
    with phase_lock_held(slug, project_root, lock_id) as acquired:
        if not acquired:
            # P-17: read the holder sentinel-first so the message names the
            # real owner (the status.json mirror can be a stale None).
            held = current_phase_lock(slug, project_root) or "?"
            sys.stderr.write(
                f"forge implement: '{slug}' phase-locked by '{held}'. "
                "Run `forge undo` to release, or wait.\n"
            )
            # DRIFT-1 W2.T3b — clear intent-resume checkpoint on lock-deny.
            _clear_implement_checkpoint(project_root)
            return fail_with_tag(ERR_LOCKED)

        try:
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
                # DRIFT-1 W2.T3b — clear intent-resume checkpoint on rejection.
                _clear_implement_checkpoint(project_root)
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

            # DRIFT-1 W2.T3b — clear intent-resume checkpoint on clean completion.
            _clear_implement_checkpoint(project_root)
            return 0

        except PromptAbortedError:
            # Pause — append history + emit copy. Lock release is owned by
            # the surrounding ``with phase_lock_held(...)``.
            append_history(
                slug,
                project_root,
                {"event": "implement-paused", "task": task.task_id},
            )
            renderer.write("")
            renderer.write(
                mentor_calmo.pause_message(
                    slug=slug, resume_command=f"forge implement {slug}", project_root=project_root
                )
            )
            # DRIFT-1 W2.T3b — pause is clean exit, clear checkpoint.
            # SPEC §3 forensic preservation aplica-se a invalid-response
            # branches (ValueError), nao a user pause.
            _clear_implement_checkpoint(project_root)
            return 130


__all__ = ["run"]
