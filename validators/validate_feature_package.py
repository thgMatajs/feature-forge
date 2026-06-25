#!/usr/bin/env python3
"""validate_feature_package.py — Feature package completeness check.

Checks that a feature directory under
`docs/forge-specs/features/{slug}/` contains all artefacts
required by the active strictness level (strict / standard / lean) from
`workflow-config.yaml § workflow.strictness-matrix`, plus that cross-refs
between artefacts are coherent.

Cross-refs validated:
- intake_ref / prd_ref / screen_analysis_ref point at real files
- task contracts under tasks/ all parse as YAML
- plan-feature-handoff.json + open-questions.yaml are always-required

Schema source: docs/schemas/forge-config.md §workflow.strictness-matrix.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from _common import (
    log,
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.utils.paths import feature_dir, workflow_config_path  # noqa: E402
from engine.utils.yaml_io import YamlIOError, read_yaml_or_default  # noqa: E402


_STRICTNESS_DEFAULT_MATRIX: dict[str, list[str]] = {
    "strict": [
        "feature-intake.md",
        "feature-prd.md",
        "screen-analysis.md",
        "bdd.md",
        "bdd.json",
        "ui-state-spec.yaml",
        "navigation-spec.yaml",
        "data-contract-spec.yaml",
        "analytics-spec.yaml",
        "test-strategy.yaml",
        "tech-spec.md",
        "task-breakdown.yaml",
        "tasks/*.yaml",
        "implementation-readiness-review.md",
    ],
    "standard": [
        "feature-intake.md",
        "feature-prd.md",
        "bdd.md",
        "navigation-spec.yaml",
        "data-contract-spec.yaml",
        "test-strategy.yaml",
        "tech-spec.md",
        "task-breakdown.yaml",
        "tasks/*.yaml",
        "implementation-readiness-review.md",
    ],
    "lean": [
        "feature-intake.md",
        "feature-prd.md",
        "bdd.md",
        "task-breakdown.yaml",
        "tasks/*.yaml",
    ],
}

_ALWAYS_REQUIRED = ["plan-feature-handoff.json", "open-questions.yaml"]


def _required_artifacts(config: dict[str, Any]) -> tuple[list[str], str]:
    """Resolve required artifact list + strictness label from workflow-config."""
    workflow = config.get("workflow") or {}
    strictness = str(workflow.get("readiness-strictness") or "strict").lower()
    matrix = workflow.get("strictness-matrix") or {}
    if not isinstance(matrix, dict):
        matrix = {}
    custom = matrix.get(strictness)
    if isinstance(custom, list) and custom:
        required = [str(x) for x in custom]
    else:
        required = list(_STRICTNESS_DEFAULT_MATRIX.get(strictness, _STRICTNESS_DEFAULT_MATRIX["strict"]))
    always = list(matrix.get("always-required") or _ALWAYS_REQUIRED)
    return required + always, strictness


def _check_artifact(feature_root: Path, rel: str) -> bool:
    """Return True if the artifact exists. Glob patterns must match at least 1."""
    if "*" in rel:
        # e.g. "tasks/*.yaml"
        return any(feature_root.glob(rel))
    return (feature_root / rel).is_file()


def _resolve_slug(root: Path, kwargs: dict[str, Any]) -> str | None:
    scope = kwargs.get("scope") or "inferred"
    given_id = kwargs.get("id")
    if scope == "feature" and given_id:
        return given_id
    if given_id and not given_id.upper().startswith("TASK-"):
        return given_id
    return None


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate the active feature package against the strictness matrix."""
    config = read_yaml_or_default(workflow_config_path(project_root), {}) or {}
    slug = _resolve_slug(project_root, kwargs)
    if not slug:
        return result_warn(
            "no feature slug provided — skipping package check",
            what_failed="no slug",
            where="--id <slug> or --scope feature --id <slug>",
            why=["validator runs only when invoked with a concrete feature slug"],
        )

    f_root = feature_dir(project_root, slug)
    if not f_root.is_dir():
        return result_fail(
            f"feature directory not found for slug {slug!r}",
            what_failed=f"missing {f_root}",
            where=str(f_root.relative_to(project_root)),
            why=[
                "forge plan didn't create the feature package yet, OR",
                "slug was renamed without moving the dir.",
            ],
            paths=make_paths(
                "Rode `forge plan <slug>` pra criar a package",
                "Você ainda está na Wave A — dir nasce depois do feature-intake.",
                "Reverter pro último plan estado bom — `forge undo last-plan`",
                "Se o slug mudou de nome, melhor refazer Wave A do zero.",
                "Trate como discovery — `forge memory forget L1 <slug>`",
                "Se a feature era exploratória, marca como discarded e segue.",
            ),
        )

    required, strictness = _required_artifacts(config)
    missing: list[str] = [rel for rel in required if not _check_artifact(f_root, rel)]

    if missing:
        what = ", ".join(missing[:5]) + (f" (+{len(missing)-5} more)" if len(missing) > 5 else "")
        return result_fail(
            f"feature package incomplete — {len(missing)} required artefactos faltando ({strictness})",
            what_failed=what,
            where=str(f_root.relative_to(project_root)),
            why=[
                f"workflow.readiness-strictness = {strictness}",
                "readiness-reviewer não vai marcar como `ready` sem esses arquivos.",
                "Sub-agents downstream (execution-conductor) refusam de rodar.",
            ],
            paths=make_paths(
                "Completar Waves B/C/D — `forge plan <slug>` continua de onde parou",
                "Fluxo natural — só faltam artefatos das próximas waves.",
                "Reverter ao último ready — `forge undo last-plan-checkpoint`",
                "Se você re-escopou a feature, vale começar do bdd novo.",
                "Baixar strictness — `forge reconfigure → workflow.readiness-strictness`",
                "Pra discovery / spike, `lean` cobre só 5 artefatos.",
            ),
        )

    yaml_errors = _validate_yaml_parses(f_root)
    if yaml_errors:
        return result_fail(
            "feature package has unparseable YAML artefatos",
            what_failed="; ".join(yaml_errors[:3]),
            where=str(f_root.relative_to(project_root)),
            why=[
                "Sub-agents downstream lê esses YAMLs como source-of-truth.",
                "YAML inválido = readiness-reviewer não consegue auditar.",
            ],
            paths=make_paths(
                "Abrir os arquivos e corrigir o YAML",
                "Tipicamente indentação ou tab/space mix.",
                "Reverter o último edit — `forge undo`",
                "Se a corrupção foi recente, undo restaura o último estado bom.",
                "Re-gerar o artefato — `forge plan <slug> --rerun=<artifact>`",
                "Quando o arquivo foi escrito por sub-agent com bug, melhor refazer.",
            ),
        )

    cross_ref_warns = _check_cross_refs(f_root)
    if cross_ref_warns:
        return result_warn(
            f"cross-refs inconsistentes: {len(cross_ref_warns)} warning(s)",
            what_failed="; ".join(cross_ref_warns[:3]),
            where=str(f_root.relative_to(project_root)),
            why=["refs entre artefatos não apontam pra arquivos que existem"],
        )

    return result_pass(
        f"feature package completa ({strictness}): {len(required)} artefatos OK"
    )


def _validate_yaml_parses(feature_root: Path) -> list[str]:
    """Return a list of "{file}: {error}" strings for unparseable YAMLs."""
    errors: list[str] = []
    for yaml_file in feature_root.glob("*.yaml"):
        try:
            read_yaml_or_default(yaml_file, None)
        except (YamlIOError, OSError, UnicodeDecodeError) as exc:
            errors.append(f"{yaml_file.name}: {exc}")
    for task_file in (feature_root / "tasks").glob("*.yaml") if (feature_root / "tasks").is_dir() else []:
        try:
            read_yaml_or_default(task_file, None)
        except (YamlIOError, OSError, UnicodeDecodeError) as exc:
            errors.append(f"tasks/{task_file.name}: {exc}")
    return errors


def _check_cross_refs(feature_root: Path) -> list[str]:
    """Soft check that *_ref keys in YAML artefatos point at real files."""
    warns: list[str] = []
    data_contract = feature_root / "data-contract-spec.yaml"
    if data_contract.is_file():
        try:
            data = read_yaml_or_default(data_contract, {}) or {}
        except (YamlIOError, OSError, UnicodeDecodeError) as exc:
            # B-008 (master review PR #15): reporta como warn em vez de
            # silenciar. Antes a função devolvia `warns` vazio em parse error,
            # escondendo cross-refs não verificados; agora pelo menos o
            # usuário vê que houve falha de parse.
            return [
                f"data-contract-spec.yaml: parse error ({exc}); cross-refs not checked"
            ]
        for key in ("prd_ref", "intake_ref", "screen_analysis_ref", "ui_state_spec_ref"):
            val = data.get(key)
            if not val or not isinstance(val, str):
                continue
            if "{{" in val:
                continue  # template placeholder, not filled yet
            ref_path = (feature_root / val).resolve()
            if not ref_path.is_file():
                warns.append(f"data-contract-spec.{key} → {val} (não encontrado)")
    return warns


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
