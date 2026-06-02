#!/usr/bin/env python3
"""validate_task_contract.py — Task contract schema check.

Validates a single `tasks/TASK-NNNN.yaml` (or all tasks under the feature when
no specific id given) against the task-contract template schema:

- schema_version == 1
- task_id matches /^TASK-\\d{4}$/
- required top-level keys present (title, layer, scope_in, scope_out,
  allowed_files, bdd_scenarios_covered, gates, evidence_required)
- depends_on entries point at sibling task files
- gates verbatim ⊇ workflow.hard-gates

Schema source: templates/task-contract.template.yaml.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from _common import (
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.utils.paths import feature_dir, workflow_config_path  # noqa: E402
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402

_TASK_ID_RE = re.compile(r"^TASK-\d{4}$")

_REQUIRED_KEYS = (
    "schema_version",
    "task_id",
    "title",
    "feature_slug",
    "layer",
    "scope_in",
    "scope_out",
    "allowed_files",
    "bdd_scenarios_covered",
    "gates",
    "evidence_required",
)

_REQUIRED_EVIDENCE = {
    "tests_passed",
    "files_touched",
    "validators_passed",
    "manual_verification_notes",
}

_KNOWN_LAYERS = {"setup", "data", "domain", "presentation", "ui", "tests", "qa"}

# Discipline §9 — external dependency schema.
_VALID_INTEGRATIONS = {"jira", "linear", "github-issues", "manual"}
_EXT_DEP_REQUIRED_KEYS = {"ticket", "integration"}


def _resolve_slug_and_task(kwargs: dict[str, Any]) -> tuple[str | None, str | None]:
    scope = kwargs.get("scope") or "inferred"
    given_id = kwargs.get("id")
    if given_id and given_id.upper().startswith("TASK-"):
        return None, given_id.upper()
    if scope == "feature" and given_id:
        return given_id, None
    if given_id:
        return given_id, None
    return None, None


def _list_task_files(feature_root: Path) -> list[Path]:
    tasks_dir = feature_root / "tasks"
    if not tasks_dir.is_dir():
        return []
    return sorted(tasks_dir.glob("TASK-*.yaml"))


def _find_task_across_features(project_root: Path, task_id: str) -> Path | None:
    """Find which feature owns a TASK-NNNN id when called with --id only."""
    base = project_root / "docs" / "feature-implementation-workflow" / "features"
    if not base.is_dir():
        return None
    for f in base.iterdir():
        if not f.is_dir():
            continue
        candidate = f / "tasks" / f"{task_id}.yaml"
        if candidate.is_file():
            return candidate
    return None


def _validate_one(task_path: Path, hard_gates: list[str]) -> list[str]:
    """Return list of human-readable violations for one task contract."""
    violations: list[str] = []
    try:
        data = read_yaml_or_default(task_path, {}) or {}
    except Exception as exc:  # noqa: BLE001
        return [f"YAML parse error: {exc}"]
    if not isinstance(data, dict):
        return ["top-level must be a mapping"]

    for key in _REQUIRED_KEYS:
        if key not in data:
            violations.append(f"missing required key: {key}")

    schema_version = data.get("schema_version")
    if schema_version != 1:
        violations.append(f"schema_version must be 1, got {schema_version!r}")

    task_id = data.get("task_id")
    if not isinstance(task_id, str) or not _TASK_ID_RE.match(task_id):
        violations.append(f"task_id must match TASK-NNNN, got {task_id!r}")

    layer = data.get("layer")
    if layer is not None and layer not in _KNOWN_LAYERS:
        violations.append(f"layer must be in {sorted(_KNOWN_LAYERS)}, got {layer!r}")

    for list_key in ("scope_in", "scope_out", "allowed_files", "bdd_scenarios_covered"):
        val = data.get(list_key)
        if val is not None and not isinstance(val, list):
            violations.append(f"{list_key} must be a list, got {type(val).__name__}")

    allowed = data.get("allowed_files") or []
    if isinstance(allowed, list):
        for glob in allowed:
            if not isinstance(glob, str) or not glob:
                violations.append(f"allowed_files entry must be non-empty string, got {glob!r}")

    gates = data.get("gates")
    if isinstance(gates, list) and hard_gates:
        missing = [g for g in hard_gates if g not in gates]
        if missing:
            violations.append(
                f"gates must include workflow.hard-gates verbatim; missing: {missing}"
            )

    evidence = data.get("evidence_required") or []
    if isinstance(evidence, list):
        present = {str(x) for x in evidence}
        missing_ev = _REQUIRED_EVIDENCE - present
        if missing_ev:
            violations.append(
                f"evidence_required must include canonical 4 fields; missing: {sorted(missing_ev)}"
            )

    depends_on = data.get("depends_on") or []
    if isinstance(depends_on, list):
        siblings = {p.stem for p in task_path.parent.glob("TASK-*.yaml")}
        for dep in depends_on:
            if not isinstance(dep, str):
                continue
            if dep not in siblings:
                violations.append(f"depends_on references unknown task: {dep}")

    # Discipline §9 — depends_on_external schema validation. Field is
    # optional (absent OR empty list = task has no external deps). When
    # present, every entry must declare ticket + integration; resolved-at
    # may be null or an ISO 8601 string. Defensive: accept kebab-case dialect.
    ext_deps = (
        data.get("depends_on_external") or data.get("depends-on-external")
    )
    if ext_deps is not None:
        if not isinstance(ext_deps, list):
            violations.append(
                f"depends_on_external must be a list, got {type(ext_deps).__name__}"
            )
        else:
            for idx, entry in enumerate(ext_deps):
                if not isinstance(entry, dict):
                    violations.append(
                        f"depends_on_external[{idx}] must be a mapping"
                    )
                    continue
                missing_keys = _EXT_DEP_REQUIRED_KEYS - set(entry.keys())
                if missing_keys:
                    violations.append(
                        f"depends_on_external[{idx}] missing keys: "
                        f"{sorted(missing_keys)}"
                    )
                ticket = entry.get("ticket")
                if not isinstance(ticket, str) or not ticket.strip():
                    violations.append(
                        f"depends_on_external[{idx}].ticket must be a non-empty string"
                    )
                integration = entry.get("integration")
                if integration not in _VALID_INTEGRATIONS:
                    violations.append(
                        f"depends_on_external[{idx}].integration must be one of "
                        f"{sorted(_VALID_INTEGRATIONS)}, got {integration!r}"
                    )
                blocking = entry.get("blocking", True)
                if not isinstance(blocking, bool):
                    violations.append(
                        f"depends_on_external[{idx}].blocking must be bool, "
                        f"got {type(blocking).__name__}"
                    )
                resolved = entry.get("resolved-at") or entry.get("resolved_at")
                if resolved is not None and not isinstance(resolved, str):
                    violations.append(
                        f"depends_on_external[{idx}].resolved-at must be null or "
                        "ISO 8601 string"
                    )

    return violations


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate one task contract (--id TASK-NNNN) or all tasks in a feature."""
    config = read_yaml_or_default(workflow_config_path(project_root), {}) or {}
    hard_gates = list((config.get("workflow") or {}).get("hard-gates") or [])

    slug, task_id = _resolve_slug_and_task(kwargs)

    targets: list[Path] = []
    if task_id:
        if slug:
            candidate = feature_dir(project_root, slug) / "tasks" / f"{task_id}.yaml"
        else:
            candidate = _find_task_across_features(project_root, task_id)
        if not candidate or not candidate.is_file():
            return result_fail(
                f"task contract {task_id} não encontrado",
                what_failed=f"missing {task_id}.yaml",
                where=str(project_root),
                why=["task-contract-writer (Wave D) ainda não rodou pra esta task"],
                paths=make_paths(
                    "Rodar Wave D — `forge plan <slug>` (continua)",
                    "task-contract-writer escreve esses YAMLs.",
                    "Reverter Wave D — `forge undo last-plan-checkpoint`",
                    "Se a wave anterior está com bug.",
                    "Re-numerar tasks — `forge plan <slug> --rerun=task-breakdown`",
                    "Se o id mudou após split.",
                ),
            )
        targets = [candidate]
    elif slug:
        f_root = feature_dir(project_root, slug)
        targets = _list_task_files(f_root)
        if not targets:
            return result_fail(
                f"nenhum task contract em {slug}/tasks/",
                what_failed="empty tasks/ directory",
                where=str(f_root / "tasks"),
                why=["Wave D não produziu nenhum TASK-NNNN.yaml"],
                paths=make_paths(
                    "Rodar Wave D — `forge plan <slug>`",
                    "task-breakdown + task-contract-writer escrevem aqui.",
                    "Reverter Wave C — `forge undo`",
                    "Se Wave D quebrou por bug em tech-spec.",
                    "Re-gerar — `forge plan <slug> --rerun=task-breakdown`",
                    "Quando o task-breakdown ficou inconsistente.",
                ),
            )
    else:
        return result_warn(
            "no slug/task-id provided — task-contract check skipped",
            what_failed="no scope",
            where="--id TASK-NNNN or --scope feature --id <slug>",
            why=["validator runs per-task or per-feature"],
        )

    all_violations: dict[str, list[str]] = {}
    for t in targets:
        viols = _validate_one(t, hard_gates)
        if viols:
            all_violations[t.name] = viols

    if not all_violations:
        return result_pass(f"task contract(s) OK ({len(targets)} validated)")

    flat = [f"{name}: {v}" for name, viols in all_violations.items() for v in viols]
    return result_fail(
        f"{len(all_violations)} task contract(s) com violações de schema",
        what_failed="; ".join(flat[:3]) + (f" (+{len(flat)-3} more)" if len(flat) > 3 else ""),
        where=str(targets[0].parent.relative_to(project_root)),
        why=[
            "task-contract template tem schema rigoroso (templates/task-contract.template.yaml)",
            "execution-conductor lê esses campos verbatim — schema drift = invented behavior",
        ],
        paths=make_paths(
            "Editar o(s) TASK-NNNN.yaml e corrigir os campos",
            "Cada violation acima diz exatamente o que falta.",
            "Re-rodar task-contract-writer — `forge plan <slug> --rerun=task-contracts`",
            "Quando o sub-agent escreveu o YAML errado.",
            "Reverter a Wave D — `forge undo last-plan-checkpoint`",
            "Se a sequência ficou inconsistente desde Wave C.",
        ),
    )


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
