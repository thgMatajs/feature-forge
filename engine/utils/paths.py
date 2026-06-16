"""Cross-platform path utilities.

Centralises all "where does file X live?" knowledge so that no other module
hardcodes paths. If the filesystem layout (`docs/design/05-filesystem-layout.md`)
ever shifts, this is the only file that has to change.

Two roots matter at runtime:
- FORGE_HOME — the canonical repo (`~/Documents/feature-forge/` by default).
- project_root — the user's project, identified by a `.claude/workflow-config.yaml`.
"""

from __future__ import annotations

import os
from pathlib import Path

# Sentinel directory + file used to locate a project root by walking up.
_WORKFLOW_DIRNAME = ".claude"
_WORKFLOW_CONFIG_FILE = "workflow-config.yaml"


class ProjectRootNotFoundError(RuntimeError):
    """Raised when no `.claude/workflow-config.yaml` is found by walking up."""


def forge_home() -> Path:
    """Return the canonical FORGE_HOME — exported by `bin/forge`."""
    home = os.environ.get("FORGE_HOME")
    if home:
        return Path(home).resolve()
    # Fallback for `python -m engine.cli` invocations outside the dispatcher.
    return Path(__file__).resolve().parents[2]


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from `start` (cwd by default) until `.claude/workflow-config.yaml` is found.

    Raises ProjectRootNotFoundError if we reach `/` without finding it. Callers
    that want a soft check should catch this and fall back to bootstrap mode
    (forge init).
    """
    cursor = (start or Path.cwd()).resolve()
    while True:
        candidate = cursor / _WORKFLOW_DIRNAME / _WORKFLOW_CONFIG_FILE
        if candidate.is_file():
            return cursor
        if cursor.parent == cursor:
            raise ProjectRootNotFoundError(
                "no .claude/workflow-config.yaml found from "
                f"{(start or Path.cwd()).resolve()} upwards. "
                "Run `forge init` from the project root."
            )
        cursor = cursor.parent


def try_find_project_root(start: Path | None = None) -> Path | None:
    """Non-raising variant — returns None when no project root is found."""
    try:
        return find_project_root(start)
    except ProjectRootNotFoundError:
        return None


def workflow_config_path(project_root: Path) -> Path:
    """Path to `.claude/workflow-config.yaml` inside a project."""
    return project_root / _WORKFLOW_DIRNAME / _WORKFLOW_CONFIG_FILE


def claude_dir(project_root: Path) -> Path:
    """The `.claude/` directory inside a project."""
    return project_root / _WORKFLOW_DIRNAME


def cards_dir(project_root: Path) -> Path:
    """Per-project card snapshots — `.claude/cards/`."""
    return claude_dir(project_root) / "cards"


def cards_canonical_dir() -> Path:
    """Canonical card library inside FORGE_HOME — `cards/`."""
    return forge_home() / "cards"


def inventory_dir(project_root: Path) -> Path:
    """Inventory snapshots — `.claude/inventory/`."""
    return claude_dir(project_root) / "inventory"


def memory_dir(project_root: Path) -> Path:
    """Memory root — `.claude/memory/`."""
    return claude_dir(project_root) / "memory"


def memory_l1_path(project_root: Path, feature_slug: str) -> Path:
    """L1 (per-feature WIP) directory for a given feature slug."""
    return memory_dir(project_root) / "L1" / feature_slug


def memory_l2_path(project_root: Path) -> Path:
    """L2 project-level memory file — `.claude/memory/L2-project.yaml`."""
    return memory_dir(project_root) / "L2-project.yaml"


def graph_db_path(project_root: Path) -> Path:
    """Graph DB — `.claude/graph.db` (SQLite, WAL mode, gitignored)."""
    return claude_dir(project_root) / "graph.db"


def hooks_dir(project_root: Path) -> Path:
    """Hook shims installed into a project — `.claude/hooks/`."""
    return claude_dir(project_root) / "hooks"


def feature_workflow_root(project_root: Path) -> Path:
    """Default feature-implementation-workflow root in the project."""
    return project_root / "docs" / "feature-implementation-workflow"


def feature_dir(project_root: Path, feature_slug: str) -> Path:
    """Per-feature directory under feature-implementation-workflow/features/."""
    return feature_workflow_root(project_root) / "features" / feature_slug


def _resolve_features_root(project_root: Path, *, subtype: str = "product") -> Path:
    """Read workflow-config.paths.feature-roots if present, else default.

    When `subtype != "product"`, the path is rerooted under `non-product/`
    per `docs/design/05-filesystem-layout.md §3.5` — keeps refactor/spike/
    chore feature packages out of the product feature folder and out of
    the similarity-graph by convention.

    A-006 (master review PR #15): movido de `engine/plan.py` pra cá. A
    função só lê `workflow_config_path` + monta paths — não tem dep de
    `engine.plan`. Mantê-la em paths.py quebra o ciclo `paths.py ↔ plan.py`
    que `feature_path` precisava resolver com lazy import.

    Backwards-compat: `engine/plan.py` re-exporta como shim.
    """
    # Lazy import: `yaml_io` é leaf, mas importá-lo no topo de paths.py
    # criaria dep desnecessária em `paths` (consumido por toda a engine).
    # O custo do lazy import é amortizado: callsites tipicos invocam
    # `_resolve_features_root` poucas vezes por execução.
    from engine.utils.yaml_io import read_yaml_or_default  # noqa: PLC0415

    cfg = read_yaml_or_default(workflow_config_path(project_root), {})
    custom_root: Path | None = None
    if isinstance(cfg, dict):
        paths = cfg.get("paths") or {}
        roots = paths.get("feature-roots") if isinstance(paths, dict) else None
        if isinstance(roots, list) and roots:
            head = roots[0]
            if isinstance(head, str):
                custom_root = (project_root / head).resolve()
        elif isinstance(roots, str):
            custom_root = (project_root / roots).resolve()

    if custom_root is not None:
        if subtype != "product":
            # Custom root is the *product* folder; non-product lives as
            # a sibling under the same parent.
            return (custom_root.parent / "non-product").resolve()
        return custom_root

    # Default per docs/design/05-filesystem-layout.md.
    base = project_root / "docs" / "feature-implementation-workflow"
    if subtype != "product":
        return (base / "non-product").resolve()
    return (base / "features").resolve()


def feature_path(project_root: Path, slug: str, *, subtype: str = "product") -> Path:
    """Resolve feature directory honouring workflow-config override + subtype.

    M-04: extracted from `engine/implement.py` and `engine/plan.py` which
    had divergent implementations — implement.py couldn't see non-product
    features because it hardcoded subtype="product".

    For `subtype="product"` the layout is the legacy v1.0 path
    (`docs/feature-implementation-workflow/features/{slug}/`). For
    refactor/spike/chore/bugfix the directory lives under
    `non-product/{slug}/` — see filesystem-layout §3.5.

    A-006 (master review PR #15): `_resolve_features_root` agora vive
    neste mesmo módulo (consolidação requerida pelo SRP — `paths.py` não
    deve depender de `engine.plan`). Lazy import de plan.py eliminado.
    """
    root = _resolve_features_root(project_root, subtype=subtype)
    if subtype == "product":
        default = (
            project_root / "docs" / "feature-implementation-workflow" / "features"
        ).resolve()
        if root == default:
            return feature_dir(project_root, slug)
    return root / slug


def ensure_dir(path: Path) -> Path:
    """mkdir -p — returns the path for chaining. Idempotent."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def forge_dir(project_root: Path) -> Path:
    """Sub-namespace canônico do forge no projeto consumidor. Spec §2."""
    return project_root / ".claude" / "forge"


def forge_config_path(project_root: Path) -> Path:
    return forge_dir(project_root) / "forge-config.yaml"


def forge_state_dir(project_root: Path) -> Path:
    return forge_dir(project_root) / "state"


def forge_cards_local_dir(project_root: Path) -> Path:
    return forge_dir(project_root) / "cards" / "local"


def forge_hooks_dir(project_root: Path) -> Path:
    return forge_dir(project_root) / "hooks"
