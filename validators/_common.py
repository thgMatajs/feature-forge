"""Shared helpers for validator scripts.

Centralises:
- result-dict shape (status/message/what-failed/where/why/paths)
- canonical 3-paths block (Fix forward / Revert / Split) per discipline §1
- argparse boilerplate (--project-root / --scope / --id)
- main() runner that prints JSON tail-on-stdout and returns the exit code
- logging to stderr so stdout stays clean for the JSON tail
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

_ENGINE_ROOT = Path(__file__).parent.parent
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

from engine.utils.paths import (  # noqa: E402  — path bootstrap above is intentional
    ProjectRootNotFoundError,
    find_project_root,
)


def make_paths(
    fix_label: str,
    fix_motive: str,
    revert_label: str,
    revert_motive: str,
    split_label: str,
    split_motive: str,
) -> list[dict[str, str]]:
    """Return the canonical 3-paths block (Fix forward / Revert / Split).

    Discipline §1: every gate violation surfaces three real options. Never two,
    never four. Mentor calmo renders them as a numbered list.
    """
    return [
        {"kind": "fix", "label": fix_label, "motive": fix_motive},
        {"kind": "revert", "label": revert_label, "motive": revert_motive},
        {"kind": "split", "label": split_label, "motive": split_motive},
    ]


def result_pass(message: str = "ok") -> dict[str, Any]:
    """Build a pass-shape result."""
    return {"status": "pass", "message": message}


def result_warn(
    message: str,
    *,
    what_failed: str = "",
    where: str = "",
    why: list[str] | None = None,
    paths: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a warn-shape result. Warn is non-blocking but surfaces in summary."""
    return {
        "status": "warn",
        "message": message,
        "what-failed": what_failed,
        "where": where,
        "why": why or [],
        "paths": paths or [],
    }


def result_fail(
    message: str,
    *,
    what_failed: str,
    where: str,
    why: list[str],
    paths: list[dict[str, str]],
) -> dict[str, Any]:
    """Build a fail-shape result. Must include the 3-paths block."""
    if len(paths) != 3:
        raise ValueError(
            f"result_fail requires exactly 3 paths (discipline §1); got {len(paths)}"
        )
    return {
        "status": "fail",
        "message": message,
        "what-failed": what_failed,
        "where": where,
        "why": why,
        "paths": paths,
    }


def log(msg: str) -> None:
    """Log to stderr so stdout stays reserved for the JSON tail."""
    print(msg, file=sys.stderr)


def build_argparser(description: str) -> argparse.ArgumentParser:
    """Return the canonical argparser shared by every validator."""
    p = argparse.ArgumentParser(description=description)
    p.add_argument(
        "--project-root",
        type=Path,
        required=False,
        help="Project root (auto-detect via .claude/workflow-config.yaml if absent)",
    )
    p.add_argument(
        "--scope",
        choices=["task", "feature", "inferred"],
        default="inferred",
        help="Scope of the verify run (mostly informational for validators)",
    )
    p.add_argument(
        "--id",
        required=False,
        help="Task id (TASK-NNNN) or feature slug, depending on scope",
    )
    return p


def resolve_root(args: argparse.Namespace) -> Path:
    """Return the project root, raising a user-readable error when missing."""
    if args.project_root is not None:
        return args.project_root.resolve()
    try:
        return find_project_root()
    except ProjectRootNotFoundError as exc:
        raise SystemExit(
            f"could not locate project root: {exc}\n"
            "pass --project-root explicitly"
        )


def emit_and_exit(result: dict[str, Any]) -> int:
    """Print the JSON tail and return the exit code.

    Convention: 0=pass, 1=fail, 2=warn. The engine's verify.py reads either the
    JSON or the exit code (whichever is present); we always emit both.
    """
    print(json.dumps(result, ensure_ascii=False))
    status = result.get("status", "pass")
    if status == "pass":
        return 0
    if status == "warn":
        return 2
    return 1


def run_cli(
    description: str,
    validator_fn: Callable[..., dict[str, Any]],
    *,
    extra_args: Callable[[argparse.ArgumentParser], None] | None = None,
) -> int:
    """Standard CLI runner shared by every validator script.

    `validator_fn(project_root, **vars(args))` returns the result dict.
    """
    parser = build_argparser(description)
    if extra_args is not None:
        extra_args(parser)
    args = parser.parse_args()
    root = resolve_root(args)
    extra = {k: v for k, v in vars(args).items() if k != "project_root"}
    result = validator_fn(root, **extra)
    return emit_and_exit(result)


# ── Capability catalog overlay loader ────────────────────────────────────────
#
# Une o catálogo canônico (parseado de docs/schemas/capability-labels.md via
# engine.cards.loader) com o overlay local em
# .claude/inventory/capability-labels.local.yaml. Guards aplicados aqui são
# fonte única — validators downstream consomem o resultado.

from dataclasses import dataclass, field  # noqa: E402

import yaml as _yaml_lib  # noqa: E402


@dataclass
class CapabilityCatalog:
    """Efectivo = canon ∪ local. `reserved` permanece sempre canon-only."""

    canon_all: frozenset[str] = field(default_factory=frozenset)
    canon_singular: frozenset[str] = field(default_factory=frozenset)
    canon_latent: frozenset[str] = field(default_factory=frozenset)
    canon_reserved: frozenset[str] = field(default_factory=frozenset)
    local_added: frozenset[str] = field(default_factory=frozenset)

    @property
    def active(self) -> frozenset[str]:
        return self.canon_all | self.local_added

    @property
    def reserved(self) -> frozenset[str]:
        return self.canon_reserved


class CatalogOverlayError(Exception):
    """Raised when capability-labels.local.yaml is malformed or violates guards."""


_FORBIDDEN_LOCAL_KEYS = {"overrides", "reserved-promotions"}


def load_catalog(project_root: Path) -> CapabilityCatalog:
    """Return canon ∪ local catalog with all guards applied.

    Guards (hard fail):
      - Local label ∈ canon.reserved → CatalogOverlayError
      - Local label ∈ canon.active → CatalogOverlayError
      - Local YAML contém chaves `overrides:` ou `reserved-promotions:` → CatalogOverlayError
      - Local YAML não-mapping → CatalogOverlayError

    Edge cases:
      - Local file ausente → catálogo canon-only (silent)
      - Local file vazio mapping → catálogo canon-only
      - Local com `added: []` → catálogo canon-only
    """
    # Import lazy pra evitar circularidade na partida dos validators.
    from engine.cards.loader import _get_catalog

    all_labels, singular, latent = _get_catalog()
    reserved = frozenset(all_labels - singular - latent)

    local_path = project_root / ".claude" / "inventory" / "capability-labels.local.yaml"
    if not local_path.is_file():
        return CapabilityCatalog(
            canon_all=all_labels,
            canon_singular=singular,
            canon_latent=latent,
            canon_reserved=reserved,
            local_added=frozenset(),
        )

    try:
        raw_text = local_path.read_text(encoding="utf-8")
        data = _yaml_lib.safe_load(raw_text) or {}
    except _yaml_lib.YAMLError as exc:
        raise CatalogOverlayError(
            f"{local_path}: YAML inválido — {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise CatalogOverlayError(
            f"{local_path}: top-level deve ser mapping, got {type(data).__name__}"
        )

    forbidden_present = sorted(set(data) & _FORBIDDEN_LOCAL_KEYS)
    if forbidden_present:
        raise CatalogOverlayError(
            f"{local_path}: chaves proibidas {forbidden_present} — "
            f"overlay não pode redefinir canon nem promover reservada. "
            f"Promoção exige ADR em docs/design/01-decisions.md."
        )

    added_raw = data.get("added") or []
    if not isinstance(added_raw, list):
        raise CatalogOverlayError(
            f"{local_path}: `added` deve ser lista, got {type(added_raw).__name__}"
        )

    added_names: set[str] = set()
    for entry in added_raw:
        if not isinstance(entry, dict):
            raise CatalogOverlayError(
                f"{local_path}: cada entrada em `added` deve ser mapping"
            )
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise CatalogOverlayError(
                f"{local_path}: cada entrada `added` precisa de `name: <str>` não-vazio"
            )
        if name in reserved:
            raise CatalogOverlayError(
                f"{local_path}: label local {name!r} está reservada no canon. "
                f"Promoção exige ADR + revisita decisão do catálogo."
            )
        if name in all_labels:
            raise CatalogOverlayError(
                f"{local_path}: label local {name!r} colide com canon ativo. "
                f"Renomeie no overlay ou remova do canon (revisita)."
            )
        added_names.add(name)

    return CapabilityCatalog(
        canon_all=all_labels,
        canon_singular=singular,
        canon_latent=latent,
        canon_reserved=reserved,
        local_added=frozenset(added_names),
    )
