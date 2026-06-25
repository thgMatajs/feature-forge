#!/usr/bin/env python3
"""validate_extension_feature.py — Extension feature mechanic enforcement (Gap 9).

For every L1 feature that declares ``extends-feature`` (non-null) in
``.claude/memory/L1/{slug}/status.json``, verifies four invariants:

- ``EXT-001`` parent slug exists as a sibling L1 directory
  ``.claude/memory/L1/{parent}/``.
- ``EXT-002`` parent's ``state == "done"`` — extensions of in-flight features
  (planning / implementing / verifying / paused / blocked-on-external) are
  rejected. Estender uma feature ainda viva polui a L1 da pai e quebra a
  invariante "1 feature = 1 ship moment".
- ``EXT-003`` derived slug differs from the parent slug — self-loop prevention.
- ``EXT-004`` dedupe: no other L1 slug declares the **same** parent with the
  **same** ``extension-scope`` (extracted from
  ``hypothesis.yaml.extension-scope`` when present; absent → empty string).
  Múltiplas extensions com scopes distintos são OK; redundância é bloqueada.

No-op pass when ``extends-feature`` is null (the default for standalone
features). 3-paths block on every hard fail per discipline §1.

Schema source: docs/schemas/memory.md §status.json (Gap 9 fields) +
docs/design/07-discipline.md §10 (Extension feature mechanic).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from _common import (
    make_paths,
    result_fail,
    result_pass,
    run_cli,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.memory.l1 import L1State, list_active_features, read_l1_status  # noqa: E402
from engine.utils.paths import lifecycle_root, memory_dir  # noqa: E402
from engine.utils.yaml_io import YamlIOError, read_yaml_or_default  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────────────


def _extension_scope(project_root: Path, slug: str) -> str:
    """Read ``extension-scope`` from this feature's hypothesis.yaml.

    Empty string when hypothesis.yaml is absent, malformed, or the field is
    not present. Empty-scope-collision is intentional: two extensions of the
    same parent with no scope declared share the same "no scope" key and
    trip EXT-004 dedupe — mentor calmo nudges the user to declare scope
    instead of silently shipping ambiguous siblings.
    """
    hyp_path = lifecycle_root(project_root) / slug / "hypothesis.yaml"
    if not hyp_path.is_file():
        return ""
    try:
        data = read_yaml_or_default(hyp_path, {}) or {}
    except (YamlIOError, OSError):
        # Best-effort: malformed YAML or unreadable file → empty scope.
        # Programming errors (AttributeError etc.) intentionally surface.
        return ""
    if not isinstance(data, dict):
        return ""
    scope = data.get("extension-scope") or data.get("extension_scope")
    if scope is None:
        return ""
    if not isinstance(scope, str):
        return ""
    return scope.strip()


def _is_extension(state: Optional[L1State]) -> bool:
    """True when this state declares a non-empty ``extends-feature``."""
    return state is not None and bool(state.extends_feature)


# ── Per-extension checks ─────────────────────────────────────────────────────


def _check_one_extension(
    project_root: Path,
    slug: str,
    state: L1State,
    seen_scopes: dict[tuple[str, str], list[str]],
) -> list[str]:
    """Return a list of failure strings for a single extension feature.

    `seen_scopes` is mutated: maps ``(parent_slug, scope)`` → list of slugs
    declaring that combination. The caller resolves EXT-004 globally after
    walking every extension (dedupe is cross-slug by definition).
    """
    fails: list[str] = []
    parent_slug = state.extends_feature or ""

    # EXT-003 — self-loop sanity. Cheapest check, run first.
    if parent_slug == slug:
        fails.append(
            f"{slug}: EXT-003 self-loop — extends-feature aponta pro próprio slug"
        )
        # Self-loops also trip EXT-001/002 misleadingly; short-circuit.
        return fails

    # EXT-001 — parent slug exists in L1.
    parent_dir = lifecycle_root(project_root) / parent_slug
    if not parent_dir.is_dir():
        fails.append(
            f"{slug}: EXT-001 parent {parent_slug!r} não existe em "
            f".claude/memory/L1/{parent_slug}/"
        )
        return fails

    # EXT-002 — parent state must be "done".
    parent_state = read_l1_status(parent_slug, project_root)
    if parent_state is None:
        # Diretório existe mas status.json ausente — tratamos como EXT-001
        # (parent não está completo o bastante pra ser estendido).
        fails.append(
            f"{slug}: EXT-001 parent {parent_slug!r} sem status.json "
            "(parent incompleto)"
        )
        return fails
    if parent_state.status != "done":
        fails.append(
            f"{slug}: EXT-002 parent {parent_slug!r} em state={parent_state.status!r}, "
            "exige 'done' (não pode estender feature ainda viva)"
        )
        return fails

    # I-002 (review fix Gap 9): check redundante "parent-feature !=
    # extends-feature" removido. Lockstep dos dois campos já é enforced
    # nos dois write paths (engine.plan._create_extension_l1 +
    # engine.memory.l1.write_l1_status), então a única forma de divergir
    # é editar status.json à mão — defender contra isso é overkill v1.
    # Plano só prevê EXT-001..004; sem código EXT-NNN dedicado, esse
    # check virava warning livre fora da taxonomia.

    # EXT-004 setup — record (parent, scope) for cross-slug dedupe.
    scope = _extension_scope(project_root, slug)
    seen_scopes[(parent_slug, scope)].append(slug)
    return fails


# ── Validator entry ──────────────────────────────────────────────────────────


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate every L1 feature that declares ``extends-feature``.

    No-op pass when no extension features exist (the common case for
    projects that haven't used the mechanic yet). Hard fail aggregates all
    EXT-001..004 hits into a single ``what-failed`` summary so the operator
    sees the full picture instead of fixing one at a time only to surface
    the next on re-run.
    """
    l1_root = lifecycle_root(project_root)
    if not l1_root.is_dir():
        # Sem L1 ainda — nada a validar (forge init não rodou).
        return result_pass("L1 ausente — nada a validar (extends-feature)")

    active_slugs = list_active_features(project_root)
    extensions: list[tuple[str, L1State]] = []
    for slug in active_slugs:
        state = read_l1_status(slug, project_root)
        if _is_extension(state):
            extensions.append((slug, state))  # type: ignore[arg-type]

    if not extensions:
        # No-op pass — caminho default pra qualquer projeto que não usa
        # extends-feature (Gap 9 ainda inativo em uso).
        return result_pass(
            f"{len(active_slugs)} feature(s) ativa(s); nenhuma declara extends-feature"
        )

    seen_scopes: dict[tuple[str, str], list[str]] = defaultdict(list)
    failures: list[str] = []

    for slug, state in extensions:
        failures.extend(_check_one_extension(project_root, slug, state, seen_scopes))

    # EXT-004 — dedupe pass after all per-extension checks accumulated.
    for (parent, scope), slugs in seen_scopes.items():
        if len(slugs) > 1:
            scope_repr = scope if scope else "(empty)"
            failures.append(
                f"EXT-004 parent={parent!r} scope={scope_repr!r} declarado por "
                f"{len(slugs)} extensions: {sorted(slugs)} — declare extension-scope "
                "distinto em hypothesis.yaml ou consolide em uma só"
            )

    if failures:
        return result_fail(
            f"{len(failures)} violação(ões) em {len(extensions)} extension(s)",
            what_failed="; ".join(failures[:3])
            + (f" (+{len(failures)-3} more)" if len(failures) > 3 else ""),
            where=".claude/memory/L1/*/status.json (+ hypothesis.yaml pra scope)",
            why=[
                "EXT-001..004 protegem a invariante de extension (Gap 9, discipline §10).",
                "Parent deve existir e estar 'done'; sem self-loop; sem dedupe de scope.",
                "extends-feature é o caminho oficial pra escopo derivado — sem ele,",
                "extensions poluem a L1 da feature pai ou geram retrabalho silencioso.",
            ],
            paths=make_paths(
                "Corrigir extends-feature no status.json da extension",
                "Apontar pra um parent done existente; ajustar parent-feature em lockstep.",
                "Reverter a extension — apagar L1/{slug}/ recém-criada",
                "Quando a extension foi criada por engano (ex.: typo no slug do parent).",
                "Renomear scope ou consolidar extensions em uma só",
                "EXT-004 quer scopes distintos por (parent, scope); declare extension-scope "
                "diferente em hypothesis.yaml ou funda as duas em uma só feature.",
            ),
        )

    return result_pass(
        f"{len(extensions)} extension(s) válida(s) — parent done, sem self-loop, sem dedupe"
    )


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
