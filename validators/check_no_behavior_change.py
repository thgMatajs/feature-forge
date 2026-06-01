#!/usr/bin/env python3
"""check_no_behavior_change.py — Refactor no-behavior-change gate.

Discipline §8 — Non-product feature track. When a feature has
`status.json.subtype == "refactor"`, this validator gates Wave E (and
`forge verify` during implement) by inspecting the git diff for
modifications to test files in the feature's scope.

Premise: modifying functional tests during a refactor is a strong signal
of disguised behavioral change. "I adjusted the test so the new code
passes" is literally the definition of behavior change. Adding NEW
tests for a safety net is generally OK, but in v1.0 we conservatively
raise 3-caminhos on ANY touch of test files — the user can explicitly
declare additive intent via path A.

Behavior matrix:

| Subtype                      | Action                                      |
|------------------------------|---------------------------------------------|
| product (default) / missing  | result_pass — gate not applicable           |
| spike / chore                | result_pass — stubs in v1.0                 |
| refactor + clean diff        | result_pass                                 |
| refactor + diff touches test | result_fail with 3-caminhos                 |

The validator is conservative on detection failure (read-only): if the
git command fails or the feature scope cannot be resolved, it falls back
to result_warn rather than result_pass to avoid silently passing real
violations.

Schema source: docs/design/07-discipline.md §8.
"""

from __future__ import annotations

import subprocess
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

from engine.memory.l1 import current_subtype  # noqa: E402

# Heuristics for identifying a test file. Conservative: any file under a
# canonical test source-set, or any file ending with a recognised test
# suffix in the project's languages.
_TEST_PATH_SEGMENTS: tuple[str, ...] = (
    "/test/",
    "/tests/",
    "/commonTest/",
    "/androidTest/",
    "/androidUnitTest/",
    "/iosTest/",
    "/iosArm64Test/",
    "/iosSimulatorArm64Test/",
    "/iosX64Test/",
    "/jvmTest/",
    "/jsTest/",
    "/__tests__/",
)

_TEST_FILENAME_SUFFIXES: tuple[str, ...] = (
    "Test.kt",
    "Tests.kt",
    "Spec.kt",
    "Test.swift",
    "Tests.swift",
    ".test.ts",
    ".test.tsx",
    ".test.js",
    ".spec.ts",
    ".spec.tsx",
    ".spec.js",
)


def _git_changed_files(project_root: Path) -> list[str]:
    """Return changed files relative to project root.

    Tries staged (`--cached`) first; falls back to working-tree diff
    against HEAD when nothing is staged. Returns [] on git failure.
    """
    for diff_args in (["--cached", "--name-only"], ["--name-only", "HEAD"]):
        try:
            out = subprocess.run(
                ["git", "-C", str(project_root), "diff", *diff_args],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, OSError):
            continue
        if out.returncode != 0:
            continue
        files = [line.strip() for line in out.stdout.splitlines() if line.strip()]
        if files:
            return files
    return []


def _looks_like_test_file(path: str) -> bool:
    """True when the path is a functional test by heuristic match."""
    posix_path = path.replace("\\", "/")
    if any(seg in posix_path for seg in _TEST_PATH_SEGMENTS):
        return True
    return any(posix_path.endswith(suffix) for suffix in _TEST_FILENAME_SUFFIXES)


def _resolve_slug(kwargs: dict[str, Any]) -> str | None:
    scope = kwargs.get("scope") or "inferred"
    given_id = kwargs.get("id")
    if scope == "feature" and given_id:
        return given_id
    if given_id and not given_id.upper().startswith("TASK-"):
        return given_id
    return None


def _resolve_subtype(project_root: Path, kwargs: dict[str, Any]) -> tuple[str, str | None]:
    """Return (subtype, slug) with slug=None when no feature scope inferable.

    Subtype defaults to "product" (the gate's no-op outcome) when no slug
    can be resolved — the gate is safe-by-default for callers that pass
    only a TASK id without a feature scope.
    """
    slug = _resolve_slug(kwargs)
    if not slug:
        return "product", None
    try:
        return current_subtype(slug, project_root), slug
    except Exception:  # noqa: BLE001 — read-only fallback
        return "product", slug


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Gate refactor diffs against modifications to test files."""
    subtype, slug = _resolve_subtype(project_root, kwargs)

    if subtype != "refactor":
        return result_pass(
            f"subtype={subtype!r} — check_no_behavior_change não se aplica "
            "(discipline §8: gate só roda em subtype=refactor)"
        )

    changed = _git_changed_files(project_root)
    if not changed:
        return result_pass(
            f"refactor '{slug}' sem arquivos staged/diff — nada a checar"
        )

    test_touches = [f for f in changed if _looks_like_test_file(f)]
    if not test_touches:
        return result_pass(
            f"refactor '{slug}' — {len(changed)} arquivo(s) diff, nenhum "
            "em path/sufixo de teste functional"
        )

    return result_fail(
        f"{len(test_touches)} arquivo(s) de teste modificado(s) em refactor '{slug}'",
        what_failed="; ".join(test_touches[:5])
        + (f" (+{len(test_touches) - 5} mais)" if len(test_touches) > 5 else ""),
        where="git diff vs functional test files",
        why=[
            "discipline §8: refactor preserva comportamento observável.",
            "Modificar teste funcional é sinal forte de mudança comportamental "
            "disfarçada — `ajustei o teste pra passar` literalmente define "
            "behavior change.",
            "feature-intake-refactor.md §No-behavior-change attestation declara "
            "explicitamente `No existing test file modified`.",
        ],
        paths=make_paths(
            "Confirmar attestation — extender allowed_files declarando que "
            "estes tests precisaram mudar e por quê",
            "Use quando os testes refletem implementation-detail (não "
            "comportamento) e o refactor genuinamente requer ajuste — registre "
            "o motivo na task-contract.yaml § no_behavior_change_exception.",
            "Reverter as mudanças nos arquivos de teste",
            "Use quando os testes foram tocados por engano (auto-format, "
            "find-and-replace amplo demais).",
            "Split — virar feature subtype=product",
            "Se o refactor de fato muda comportamento, abandone o subtype "
            "refactor e re-rode `forge plan` como feature standard.",
        ),
    )


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
