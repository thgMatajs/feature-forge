#!/usr/bin/env python3
"""check_no_invented_behavior.py — Anti-invented-behavior gate.

Inspects the currently staged code and checks that:
- Every analytics event emitted via `logEvent("...")` is declared in
  `analytics-spec.yaml`
- Every test-id string used via `testTag("...")` /
  `accessibilityIdentifier("...")` is declared in the observability contracts
  under `shared/core/.../observability/` (when the project has them)
- Every log/event/test-id string introduced in staged files exists in the
  observability source-of-truth.

This is a *defensive* gate. It greps staged files only — no AST. False
positives are surfaced as warn, not fail.

Schema sources: templates/analytics-spec.template.yaml +
.claude/rules/observability.md.
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
from _diff import git_staged_files  # M-09 dedupe: reuse shared helper (with -M80% rename detection)

# A-014 (master review PR #15): `sys.path.insert` precisa rodar ANTES de
# qualquer `from engine....` — antes ficava entre os blocos, funcionava por
# coincidência da ordem do interpretador mas violava PEP-8 e seria quebrado
# silenciosamente por um futuro reorder de linter. Único `# noqa: E402` no
# bloco abaixo cobre os imports que dependem do path patch.
sys.path.insert(0, str(Path(__file__).parent.parent))  # noqa: E402

from engine.utils.paths import feature_dir  # noqa: E402
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402


_LOG_EVENT_RE = re.compile(r"""logEvent\s*\(\s*["']([a-z0-9_]+)["']""")
_TEST_TAG_RE = re.compile(
    r"""(?:testTag|accessibilityIdentifier)\s*\(\s*["']([a-z0-9_]+)["']"""
)


def _resolve_slug(kwargs: dict[str, Any]) -> str | None:
    scope = kwargs.get("scope") or "inferred"
    given_id = kwargs.get("id")
    if scope == "feature" and given_id:
        return given_id
    if given_id and not given_id.upper().startswith("TASK-"):
        return given_id
    return None


def _collect_analytics_events(feature_root: Path) -> set[str]:
    spec = feature_root / "analytics-spec.yaml"
    if not spec.is_file():
        return set()
    data = read_yaml_or_default(spec, {}) or {}
    events: set[str] = set()
    for ev in data.get("events") or []:
        if isinstance(ev, dict) and isinstance(ev.get("name"), str):
            events.add(ev["name"])
    return events


def _collect_observability_constants(project_root: Path) -> set[str]:
    """Walk shared/core/observability/ for `const val FOO = "bar"` strings.

    Falls back to empty set when the project has no observability dir — the
    gate will then surface staged strings as warn (best-effort).
    """
    out: set[str] = set()
    candidates = [
        project_root / "shared" / "core" / "src" / "commonMain" / "kotlin",
        project_root / "shared" / "src" / "commonMain" / "kotlin",
    ]
    for base in candidates:
        if not base.is_dir():
            continue
        for kt in base.rglob("*.kt"):
            if "observability" not in kt.as_posix().lower():
                continue
            try:
                text = kt.read_text(encoding="utf-8")
            except OSError:
                continue
            for m in re.finditer(r'\bconst\s+val\s+\w+\s*=\s*"([^"]+)"', text):
                out.add(m.group(1))
    return out


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Scan staged files for analytics events + test-tags not in contracts."""
    staged = git_staged_files(
        project_root,
        extensions={".kt", ".kts", ".swift", ".ts", ".tsx", ".js"},
    )
    if not staged:
        return result_pass("nenhum arquivo staged — nada a checar")

    slug = _resolve_slug(kwargs)

    declared_events: set[str] = set()
    if slug:
        f_root = feature_dir(project_root, slug)
        if f_root.is_dir():
            declared_events = _collect_analytics_events(f_root)

    declared_ids = _collect_observability_constants(project_root)

    found_events: dict[str, str] = {}
    found_tags: dict[str, str] = {}
    for file in staged:
        try:
            text = file.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _LOG_EVENT_RE.finditer(text):
            ev = m.group(1)
            if ev not in declared_events and ev not in found_events:
                found_events[ev] = str(file.relative_to(project_root))
        for m in _TEST_TAG_RE.finditer(text):
            tag = m.group(1)
            if tag not in declared_ids and tag not in found_tags:
                found_tags[tag] = str(file.relative_to(project_root))

    if not found_events and not found_tags:
        return result_pass(
            f"sem invented behavior detectado ({len(staged)} staged files)"
        )

    invented = []
    if found_events:
        invented.extend(f"event {e} @ {f}" for e, f in list(found_events.items())[:3])
    if found_tags:
        invented.extend(f"testTag {t} @ {f}" for t, f in list(found_tags.items())[:3])

    return result_fail(
        f"{len(found_events)} event(s) + {len(found_tags)} test-tag(s) sem declaração no contrato",
        what_failed="; ".join(invented),
        where="staged files diff",
        why=[
            "observability.md: NUNCA hardcode IDs ou eventos no código de feature.",
            "Tudo vem de shared:core/observability/ + analytics-spec.yaml.",
            "Hard gate: no-invented-behavior.",
        ],
        paths=make_paths(
            "Declarar os eventos/IDs nos contratos antes do commit",
            "analytics-spec.yaml + shared/core/observability/{Feature}Analytics.kt.",
            "Reverter as adições invented — `git restore --staged <file>` + ajustar",
            "Se foi código experimental, tira dos staged.",
            "Levantar elicitação — `forge plan <slug> --rerun=analytics-spec`",
            "Se os eventos novos requerem decisão de produto.",
        ),
    )


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
