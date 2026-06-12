#!/usr/bin/env python3
"""validate_inventory.py — Inventory snapshots (design-system, i18n, conventions).

Validates `.claude/inventory/{design-system,i18n,conventions}.yaml`:

- Each YAML file parses
- schema-version == 1 in each
- DS components declare at least one platform path (INV-DS-002) and the path
  points at a real file on disk
- i18n source-of-truth.path exists (INV-I18N-002)
- conventions.state-pattern.name ∈ known set (INV-CONV-004)

Schema source: docs/schemas/inventories.md (INV-DS / INV-I18N / INV-CONV).
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

from engine.utils.paths import inventory_dir  # noqa: E402
from engine.utils.yaml_io import YamlIOError, read_yaml_or_default  # noqa: E402


_KNOWN_STATE_PATTERNS = {"stateui", "stateflow-pure", "custom-sealed"}
_KNOWN_DI_PATTERNS = {"koin-annotations", "koin-dsl", "hilt", "manual"}


def _validate_design_system(project_root: Path, path: Path) -> list[str]:
    if not path.is_file():
        return [f"design-system.yaml ausente em {path}"]
    try:
        data = read_yaml_or_default(path, {}) or {}
    except (YamlIOError, OSError, UnicodeDecodeError) as exc:
        return [f"design-system.yaml YAML error: {exc}"]
    if not isinstance(data, dict):
        return ["design-system.yaml: top-level not mapping"]
    out: list[str] = []
    if data.get("schema-version") != 1:
        out.append("INV-DS-001: schema-version must be 1")
    components = data.get("components") or []
    if not isinstance(components, list):
        return out + ["components must be a list"]
    for idx, c in enumerate(components):
        if not isinstance(c, dict):
            out.append(f"components[{idx}] must be mapping")
            continue
        paths = c.get("paths") or {}
        if not isinstance(paths, dict) or not any(v for v in paths.values() if isinstance(v, str)):
            out.append(f"INV-DS-002: components[{idx}] needs ≥1 platform path")
            continue
        # warn-level: paths point at real files
        for plat, p in paths.items():
            if not isinstance(p, str) or not p:
                continue
            target = (project_root / p).resolve()
            if not target.exists():
                out.append(f"INV-DS-002-WARN: components[{idx}].paths.{plat} {p!r} not on disk")
    return out


def _validate_i18n(project_root: Path, path: Path) -> list[str]:
    if not path.is_file():
        return [f"i18n.yaml ausente em {path}"]
    try:
        data = read_yaml_or_default(path, {}) or {}
    except (YamlIOError, OSError, UnicodeDecodeError) as exc:
        return [f"i18n.yaml YAML error: {exc}"]
    if not isinstance(data, dict):
        return ["i18n.yaml: top-level not mapping"]
    out: list[str] = []
    if data.get("schema-version") != 1:
        out.append("INV-I18N-001: schema-version must be 1")
    src = data.get("source-of-truth") or {}
    src_path = src.get("path") if isinstance(src, dict) else None
    if isinstance(src_path, str) and src_path:
        target = (project_root / src_path).resolve()
        if not target.exists():
            out.append(f"INV-I18N-002: source-of-truth.path {src_path!r} not on disk")
    return out


def _validate_conventions(path: Path) -> list[str]:
    if not path.is_file():
        return [f"conventions.yaml ausente em {path}"]
    try:
        data = read_yaml_or_default(path, {}) or {}
    except (YamlIOError, OSError, UnicodeDecodeError) as exc:
        return [f"conventions.yaml YAML error: {exc}"]
    if not isinstance(data, dict):
        return ["conventions.yaml: top-level not mapping"]
    out: list[str] = []
    if data.get("schema-version") != 1:
        out.append("INV-CONV-001: schema-version must be 1")
    state = (data.get("state-pattern") or {}).get("name") if isinstance(data.get("state-pattern"), dict) else None
    if state and state not in _KNOWN_STATE_PATTERNS:
        out.append(f"INV-CONV-004: state-pattern.name {state!r} not in {sorted(_KNOWN_STATE_PATTERNS)}")
    di = (data.get("di-pattern") or {}).get("name") if isinstance(data.get("di-pattern"), dict) else None
    if di and di not in _KNOWN_DI_PATTERNS:
        out.append(f"INV-CONV-005: di-pattern.name {di!r} not in {sorted(_KNOWN_DI_PATTERNS)}")
    return out


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate the three inventory snapshots."""
    inv = inventory_dir(project_root)
    ds_violations = _validate_design_system(project_root, inv / "design-system.yaml")
    i18n_violations = _validate_i18n(project_root, inv / "i18n.yaml")
    conv_violations = _validate_conventions(inv / "conventions.yaml")

    hard: list[str] = []
    soft: list[str] = []
    for v in ds_violations + i18n_violations + conv_violations:
        if "-WARN" in v:
            soft.append(v)
        else:
            hard.append(v)

    if hard:
        return result_fail(
            f"{len(hard)} violação(ões) hard em inventory snapshots",
            what_failed="; ".join(hard[:3]) + (f" (+{len(hard)-3} more)" if len(hard) > 3 else ""),
            where=str(inv.relative_to(project_root)),
            why=[
                "inventory é factual snapshot — quebrado, sub-agents partem de dados errados.",
                "INV-DS / INV-I18N / INV-CONV blocking rules em docs/schemas/inventories.md.",
            ],
            paths=make_paths(
                "Re-extrair — `forge reconfigure → re-extrair inventory <name>`",
                "Re-scan do projeto regenera o snapshot.",
                "Restaurar do git — `git checkout .claude/inventory/`",
                "Se a edição manual ficou inconsistente.",
                "Editar manualmente o YAML pra corrigir os campos",
                "Cada violation diz exatamente o campo em falta.",
            ),
        )

    if soft:
        return result_warn(
            f"{len(soft)} warning(s) — paths em design-system não batem no disco",
            what_failed="; ".join(soft[:3]),
            where=str(inv.relative_to(project_root)),
            why=["Componentes movidos/renomeados? Inventory stale."],
        )

    return result_pass(f"inventory snapshots OK (3 arquivos validados)")


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
