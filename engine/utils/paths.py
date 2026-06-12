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


def feature_path(project_root: Path, slug: str, *, subtype: str = "product") -> Path:
    """Resolve feature directory honouring workflow-config override + subtype.

    M-04: extracted from `engine/implement.py` and `engine/plan.py` which
    had divergent implementations — implement.py couldn't see non-product
    features because it hardcoded subtype="product".

    For `subtype="product"` the layout is the legacy v1.0 path
    (`docs/feature-implementation-workflow/features/{slug}/`). For
    refactor/spike/chore/bugfix the directory lives under
    `non-product/{slug}/` — see filesystem-layout §3.5.
    """
    # Lazy imports break circular deps with engine.plan (which historically
    # owns _resolve_features_root). Re-locate it here when the consolidation
    # of _resolve_features_root happens — out of scope for M-04.
    from engine.plan import _resolve_features_root  # noqa: PLC0415

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
