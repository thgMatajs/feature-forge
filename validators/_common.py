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
