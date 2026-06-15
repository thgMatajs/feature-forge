#!/usr/bin/env python3
"""validate_screen_analysis.py — Screen analysis + ui-state-spec consistency.

Validates that:
- `screen-analysis.md` exists (when strictness=strict)
- `ui-state-spec.yaml` parses and uses canonical StateUI states
  (Idle/Processing/Processed/Error) where applicable
- Each declared screen references components that exist in
  `inventory/design-system.yaml` (warn-level when missing — components may be
  new for this feature)

Schema sources: templates/screen-analysis.template.md +
templates/ui-state-spec.template.yaml + docs/schemas/inventories.md.
"""

from __future__ import annotations

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

from engine.utils.paths import feature_dir, inventory_dir  # noqa: E402
from engine.utils.yaml_io import YamlIOError, read_yaml_or_default  # noqa: E402


_CANONICAL_STATES = {"idle", "processing", "processed", "error", "loading", "success"}


def _resolve_slug(kwargs: dict[str, Any]) -> str | None:
    scope = kwargs.get("scope") or "inferred"
    given_id = kwargs.get("id")
    if scope == "feature" and given_id:
        return given_id
    if given_id and not given_id.upper().startswith("TASK-"):
        return given_id
    return None


def _load_ds_components(project_root: Path) -> set[str]:
    ds = inventory_dir(project_root) / "design-system.yaml"
    data = read_yaml_or_default(ds, {}) or {}
    components = data.get("components") or []
    out: set[str] = set()
    for c in components:
        if isinstance(c, dict) and isinstance(c.get("name"), str):
            out.add(c["name"])
    return out


def _collect_components_referenced(ui_state: dict[str, Any]) -> set[str]:
    """Walk the ui-state-spec dict and harvest any string that looks like a
    DS component name (PascalCase, starting with Meo* or Capital). We use a
    cheap surface scan — the template doesn't have a single canonical field
    listing components, so we look at all leaf strings under screens.*
    """
    refs: set[str] = set()
    screens = ui_state.get("screens") or []
    if not isinstance(screens, list):
        return refs

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if value and value[0].isupper() and "." not in value and " " not in value:
                refs.add(value)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)

    walk(screens)
    return refs


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate screen-analysis.md + ui-state-spec.yaml for the active feature."""
    slug = _resolve_slug(kwargs)
    if not slug:
        return result_warn(
            "no feature slug provided — screen-analysis check skipped",
            what_failed="no slug",
            where="--scope feature --id <slug>",
            why=["screen-analysis is per-feature"],
        )

    f_root = feature_dir(project_root, slug)
    screen_md = f_root / "screen-analysis.md"
    ui_spec = f_root / "ui-state-spec.yaml"

    if not ui_spec.is_file():
        return result_warn(
            "ui-state-spec.yaml ausente — feature pode ter strictness=lean/standard",
            what_failed="missing ui-state-spec.yaml",
            where=str(ui_spec.relative_to(project_root)),
            why=["Wave B (screen-analysis) opcional em lean/standard"],
        )

    try:
        ui_data = read_yaml_or_default(ui_spec, {}) or {}
    except (YamlIOError, OSError, UnicodeDecodeError) as exc:
        return result_fail(
            "ui-state-spec.yaml inválido (YAML parse error)",
            what_failed=str(exc),
            where=str(ui_spec.relative_to(project_root)),
            why=["Sub-agents UI parsing falha"],
            paths=make_paths(
                "Corrigir o YAML manualmente",
                "Tipicamente indentação ou string sem aspas.",
                "Reverter o último edit — `forge undo`",
                "Se a corrupção foi recente.",
                "Re-gerar — `forge plan <slug> --rerun=ui-state-spec`",
                "Se o sub-agent escreveu o YAML errado.",
            ),
        )

    if not isinstance(ui_data, dict):
        return result_fail(
            "ui-state-spec.yaml: top-level deve ser mapping",
            what_failed=f"got {type(ui_data).__name__}",
            where=str(ui_spec.relative_to(project_root)),
            why=["Template requer schema com chaves top-level (schema_version, screens, ...)"],
            paths=make_paths(
                "Re-gerar o arquivo do template",
                "templates/ui-state-spec.template.yaml.",
                "Reverter o último edit — `forge undo`",
                "Se foi sobrescrito por engano.",
                "Re-rodar screen-analysis — `forge plan <slug> --rerun=ui-state-spec`",
                "Quando o sub-agent quebrou o shape.",
            ),
        )

    violations: list[str] = []
    if ui_data.get("schema_version") != 1:
        violations.append(f"schema_version must be 1, got {ui_data.get('schema_version')!r}")

    screens = ui_data.get("screens")
    if not isinstance(screens, list) or not screens:
        violations.append("screens must be a non-empty list")

    if isinstance(screens, list):
        for idx, screen in enumerate(screens):
            if not isinstance(screen, dict):
                violations.append(f"screens[{idx}] must be a mapping")
                continue
            states = screen.get("states") or screen.get("ui_states") or []
            if isinstance(states, list) and states:
                for s in states:
                    name = s.get("name") if isinstance(s, dict) else s
                    if isinstance(name, str) and name.lower() not in _CANONICAL_STATES:
                        violations.append(
                            f"screens[{idx}].states contém '{name}' fora dos canônicos "
                            f"({sorted(_CANONICAL_STATES)})"
                        )

    if violations:
        return result_fail(
            f"ui-state-spec.yaml com {len(violations)} violação(ões)",
            what_failed="; ".join(violations[:3]),
            where=str(ui_spec.relative_to(project_root)),
            why=[
                "StateUI<T> sealed class é regra absoluta (architecture_kmp.md).",
                "ViewModels usam estados canônicos — divergir aqui = invented behavior.",
            ],
            paths=make_paths(
                "Editar o YAML usando states canônicos (Idle/Processing/Processed/Error)",
                "Substituir custom sealed por StateUI<T>.",
                "Re-rodar screen-analysis — `forge plan <slug> --rerun=ui-state-spec`",
                "Quando o sub-agent inventou estados.",
                "Reverter Wave B — `forge undo last-plan-checkpoint`",
                "Se Wave A precisa ajuste antes.",
            ),
        )

    ds_components = _load_ds_components(project_root)
    refs = _collect_components_referenced(ui_data)
    meo_refs = {r for r in refs if r.startswith("Meo")}
    unknown_meo = meo_refs - ds_components
    if unknown_meo:
        return result_warn(
            f"{len(unknown_meo)} Meo* component(s) referenciado(s) mas ausente(s) do inventory",
            what_failed=", ".join(sorted(unknown_meo)[:5]),
            where=str(ui_spec.relative_to(project_root)),
            why=[
                "inventory/design-system.yaml é source-of-truth dos componentes.",
                "Componentes novos podem ser legítimos — mas precisam virar inventory entry.",
            ],
        )

    msg = "screen-analysis + ui-state-spec OK"
    if not screen_md.is_file():
        msg += " (screen-analysis.md ausente, mas strictness pode permitir)"
    return result_pass(msg)


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
