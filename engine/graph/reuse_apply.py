"""Apply handler for reuse-intelligence proposals.

When the user picks "aplicar" on a duplicate/promote/migration proposal,
this module materializes a feature-intake stub under
``docs/feature-implementation-workflow/non-product/{slug}/feature-intake.md``
plus a ``status.json`` companion. The refactor-subtype flow (Gap 2) takes
over from there when the user runs ``forge plan {slug}``.

No L2 mutation, no code edits. The intake captures **what** to consolidate;
the human (with ``forge plan`` + ``forge implement``) decides **how**.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from engine.memory.distiller import DistillationProposal
from engine.memory.l1 import L1State, write_l1_status
from engine.utils.paths import forge_home
from engine.utils.template_render import render_template

# Relative location inside the project for the refactor track. Mirrors what
# ``docs/design/05-filesystem-layout.md`` describes as the "non-product
# feature track".
_NON_PRODUCT_DIR = "docs/feature-implementation-workflow/non-product"
_INTAKE_TEMPLATE = "templates/feature-intake-refactor.template.md"

# Maps internal category → human-readable migration plan paragraph that goes
# into the intake's §Migration plan section.
_MIGRATION_PLAN_BY_CATEGORY: dict[str, str] = {
    "duplicate-within-module": (
        "1. Create the canonical extension at `{suggested_target}`.\n"
        "2. Update each consumer to import from the new location.\n"
        "3. Delete the duplicate copies.\n"
        "4. Re-run `forge reconfigure` (graph rebuild) and confirm the "
        "finding disappears."
    ),
    "duplicate-cross-module": (
        "1. Promote the helper to `{suggested_target}` (smallest common "
        "ancestor reachable from every affected module).\n"
        "2. Ensure each affected Gradle module already depends on the "
        "target — add `implementation(project(...))` if missing.\n"
        "3. Migrate consumers; delete per-module duplicates.\n"
        "4. Re-run `forge reconfigure` to confirm."
    ),
    "redundant-platform-specific": (
        "1. Keep the shared `commonMain` definition as canonical.\n"
        "2. Delete the Android-side copy.\n"
        "3. Ensure androidApp / shared:*:androidMain consumers resolve to the "
        "shared symbol (no import change needed when packages align).\n"
        "4. Re-run `forge reconfigure`."
    ),
    "review-near-duplicate-helper": (
        "Same signature, different body — DECIDE FIRST:\n"
        "  (a) One is canonical and the others are bugs/drift → fix and "
        "consolidate (then re-run as `consolidate-*`).\n"
        "  (b) The variants are intentional (different domains) → rename "
        "to disambiguate.\n"
        "This proposal does NOT prescribe a fix — review manually."
    ),
    "kmp-migration-candidate": (
        "1. Confirm semantics — Swift and Kotlin bodies share token "
        "similarity but ARE NOT byte-for-byte identical.\n"
        "2. If equivalent: delete the Swift extension; call the shared "
        "Kotlin helper via SKIE-generated binding.\n"
        "3. If divergent on purpose: reject this proposal so it doesn't "
        "resurface."
    ),
    "consolidate-ts-helper": (
        "1. Extract the helper to `{suggested_target}`.\n"
        "2. Update imports across the duplicated files.\n"
        "3. Delete the duplicates.\n"
        "4. Re-run `forge reconfigure`."
    ),
}


def apply_reuse_intelligence_proposal(
    project_root: Path,
    proposal: DistillationProposal,
) -> Path:
    """Write the intake + status.json; return the intake file path.

    The status.json is written via ``engine.memory.l1.write_l1_status`` so it
    matches the canonical L1State schema — that's how ``forge plan {slug}``
    discovers the existing refactor subtype and skips Wave A discovery.
    """
    slug = _slug_for(proposal)
    intake_dir = project_root / _NON_PRODUCT_DIR / slug
    intake_dir.mkdir(parents=True, exist_ok=True)
    intake_path = intake_dir / "feature-intake.md"

    template_path = forge_home() / _INTAKE_TEMPLATE
    if not template_path.exists():
        raise FileNotFoundError(
            f"refactor template missing: {template_path} — "
            "Gap 2 (refactor subtype) precondition not met"
        )

    payload = _inner_payload(proposal)
    locations = payload.get("locations") or []

    context = _build_template_context(slug, proposal, payload, locations)
    rendered = render_template(template_path.read_text(encoding="utf-8"), context)
    rendered = _populate_dynamic_blocks(rendered, proposal, payload, locations, slug)

    intake_path.write_text(rendered, encoding="utf-8")

    now = datetime.now(timezone.utc).isoformat()
    state = L1State(
        feature_slug=slug,
        status="planning",
        last_action_at=now,
        last_action_kind="reuse-intelligence-apply",
        subtype="refactor",
        raw={
            "source-proposal-id": proposal.id,
            "source-kind": proposal.kind,
            "category": payload.get("category"),
            "suggested-target": payload.get("suggested_target"),
            "fingerprint": proposal.fingerprint,
        },
    )
    write_l1_status(state, project_root)

    return intake_path


def _inner_payload(proposal: DistillationProposal) -> dict:
    """Reach into the nested ``proposed-change.payload`` produced by the
    distiller serializer. Falls back to the outer payload when the proposal
    was built directly (tests / programmatic apply)."""
    outer = proposal.payload or {}
    inner = outer.get("payload")
    if isinstance(inner, dict) and inner:
        return inner
    return outer


def _slug_for(proposal: DistillationProposal) -> str:
    """Deterministic kebab-case slug for the refactor track."""
    payload = _inner_payload(proposal)
    receiver = payload.get("receiver_type") or ""
    name = payload.get("symbol_name") or ""
    parts = [_kebabify(receiver) if receiver else "", _kebabify(name)]
    body = "-".join(p for p in parts if p)
    if not body:
        body = _kebabify(proposal.title) or proposal.id.lower()
    return f"refactor-{body}".strip("-")


_KEBAB_PARTS = re.compile(r"[A-Za-z][a-z0-9]+|[A-Z]+(?![a-z])|\d+")


def _kebabify(text: str) -> str:
    matches = _KEBAB_PARTS.findall(text or "")
    return "-".join(m.lower() for m in matches if m).strip("-")


def _build_template_context(
    slug: str,
    proposal: DistillationProposal,
    payload: dict,
    locations: Iterable[dict],
) -> dict[str, str]:
    receiver = payload.get("receiver_type") or "(top-level)"
    symbol_name = payload.get("symbol_name") or proposal.title
    feature_name = f"{receiver}.{symbol_name}"
    paths = sorted({str(loc.get("path", "")) for loc in locations if loc.get("path")})
    languages = sorted({str(loc.get("language", "")) for loc in locations if loc.get("language")})
    platforms = ", ".join(_platforms_from_languages(languages)) or "android, ios, web"

    return {
        "feature_slug": slug,
        "generated_at_iso8601": datetime.now(timezone.utc).isoformat(),
        "source_type": "ticket",
        "source_ref_or_none": proposal.id,
        "human_readable_feature_name": feature_name,
        "owner_or_null": "(assign)",
        "active_platforms_comma_separated": platforms,
        "ticket_link_or_none": proposal.id,
        "screenshots_count": "0",
        "screenshots_relative_paths_csv_or_none": "none",
        "description_origin": "init-scan",
        "technical_debt_paragraph": proposal.description
        or f"Reuse opportunity detected for `{feature_name}` across {len(paths)} location(s).",
        "root_cause_paragraph_or_unknown": _root_cause_from_category(payload.get("category")),
        "validation_paragraph": (
            "Re-run `forge reconfigure` (graph rebuild) and confirm the matching "
            f"reuse_findings row for fingerprint `{proposal.fingerprint}` disappears. "
            "Run the project's quality gates (`./gradlew ...`, `swiftlint`, "
            "`npm run build`) on each affected module."
        ),
    }


def _platforms_from_languages(languages: list[str]) -> list[str]:
    out: list[str] = []
    for lang in languages:
        if lang == "kotlin":
            out.append("android")
        elif lang == "swift":
            out.append("ios")
        elif lang in {"typescript", "javascript"}:
            out.append("web")
    return sorted(set(out))


def _root_cause_from_category(category: str | None) -> str:
    if category == "duplicate-within-module":
        return (
            "Helper foi adicionado por features distintas no mesmo módulo Gradle "
            "sem antes checar `*Extension.kt` existentes — falta sinal de reuse-existing."
        )
    if category == "duplicate-cross-module":
        return (
            "Múltiplos módulos Gradle implementaram a mesma extensão independentemente. "
            "Geralmente sinal de helper de plataforma/firebase/util que deveria viver no core."
        )
    if category == "redundant-platform-specific":
        return (
            "Android override foi adicionado antes da implementação ir pro `commonMain`, "
            "ou ficou esquecido depois da migração shared."
        )
    if category == "review-near-duplicate-helper":
        return (
            "Duas (ou mais) features evoluíram o mesmo nome em direções diferentes — "
            "pode ser drift acidental ou divergência intencional. Decidir antes de mexer."
        )
    if category == "kmp-migration-candidate":
        return (
            "Implementação Swift foi escrita antes da contraparte Kotlin shared existir "
            "(ou independentemente dela). SKIE permite reuse cross-language hoje."
        )
    if category == "duplicate-ts-helper":
        return (
            "Helper TypeScript top-level foi duplicado entre componentes/features sem "
            "passar pelo `util/` do módulo."
        )
    return "Root cause unknown — registered as Q-NNN (TODO: investigate during refactor planning)."


def _populate_dynamic_blocks(
    rendered: str,
    proposal: DistillationProposal,
    payload: dict,
    locations: list[dict],
    slug: str,
) -> str:
    """Replace placeholder bullets with concrete content from the proposal."""
    suggested = payload.get("suggested_target") or "manual review"

    files_block = "\n".join(
        f"- {loc.get('path', '?')}:{loc.get('line_start', 0)} (update or delete)"
        for loc in locations
    ) or "- (no specific files captured)"

    before_lines = []
    for loc in locations:
        module = loc.get("module") or "?"
        ss = loc.get("source_set") or "main"
        path = loc.get("path") or "?"
        before_lines.append(f"  • {module} / {ss}: {path}")
    before_block = "\n".join(before_lines) or "  • (no locations)"

    after_block = f"  • Canonical at: {suggested}\n  • Consumers updated to import from canonical location."

    constraints = []
    similarity = payload.get("similarity_score")
    if similarity is not None:
        constraints.append(f"- Cross-language token similarity: {float(similarity):.2f}")
    if payload.get("body_hash"):
        constraints.append(f"- Body hash equivalence: {payload['body_hash']}")
    constraints.append(f"- Source trigger: {payload.get('source_trigger', 'init-scan')}")
    constraints_block = "\n".join(constraints)

    migration_template = _MIGRATION_PLAN_BY_CATEGORY.get(
        payload.get("category") or "",
        "(no canned migration plan — author it during `forge plan`)",
    )
    migration = migration_template.format(suggested_target=suggested)

    rendered = rendered.replace(
        "- {{file_or_group_1}} ({{move_rename_delete_update_create}})\n"
        "- {{file_or_group_2}} ({{move_rename_delete_update_create}})",
        files_block,
    )
    rendered = rendered.replace("- {{before_state_bullet_1}}", before_block)
    rendered = rendered.replace("- {{after_state_bullet_1}}", after_block)
    rendered = rendered.replace(
        "- {{constraint_1_with_source_citation}}\n- {{constraint_2_with_source_citation}}",
        constraints_block,
    )
    rendered = rendered.replace(
        "- Q-{{NNN}}: {{question_text}} — {{why_it_blocks_intake}}\n"
        "- Q-{{NNN}}: {{...}}",
        f"- Q-001: Validate that consolidation preserves semantics (especially for "
        f"`{slug}`). — Blocks Wave A until migration plan is sanity-checked.\n"
        f"\n## Migration plan\n\n{migration}",
    )

    return rendered


__all__ = [
    "apply_reuse_intelligence_proposal",
]
