"""Card loader + `card.yaml` validation.

Loads a card directory into a `CardManifest` and runs schema validation
(CARD-001..CARD-018 from `docs/schemas/card.md §Validation`).

The capability-label catalog (`docs/schemas/capability-labels.md`) is parsed
lazily from the markdown source-of-truth via `_parse_capability_catalog`.
Adding labels is a one-file change (the markdown table).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml as _yaml_lib

from ..utils.paths import forge_home
from ..utils.yaml_io import YamlIOError, read_yaml
from . import CardError, CardConflictError

# ── Canonical catalog (hardcoded, FOLLOWUP: parse capability-labels.md) ──────

_KNOWN_CATEGORIES: frozenset[str] = frozenset(
    {
        "language",
        "kmp",
        "ui",
        "di",
        "dependency-injection",
        "navigation",
        "network",
        "backend",
        "persistence",
        "observability",
        "auth",
        "storage",
        "testing",
        "build",
        "design-system",
        "ticketing",
    }
)

_KNOWN_MATURITIES: frozenset[str] = frozenset(
    {"experimental", "beta", "stable", "deprecated"}
)

_KNOWN_MERGE_MODES: frozenset[str] = frozenset(
    {
        "append-section",
        "replace-section",
        "before-section",
        "after-section",
        "merge-keys",
    }
)

_KNOWN_RUNS_ON: frozenset[str] = frozenset(
    {
        "pre-commit",
        "pre-push",
        "verify-task",
        "forge-doctor",
        "post-init",
        "post-reconfigure",
    }
)

_KNOWN_SEVERITIES: frozenset[str] = frozenset({"warn", "error", "block"})

_KNOWN_HOOK_EVENTS: frozenset[str] = frozenset(
    {"pre-commit", "pre-push", "post-edit", "post-subagent", "post-init"}
)

# ── Capability-label catalog parser ──────────────────────────────────────────
# Parsed lazily from `docs/schemas/capability-labels.md` (source of truth).
# Each Markdown table row is:
#   | `label` | family | provider(s) | description | Type |
# Type column drives Singular / Latente / Auxiliar / Reservada classification.

# Main 5-column table (Foundation, DI, UI, ...): Label | Family | Provider | Description | Type
_LABEL_ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|[^|]*\|[^|]*\|[^|]*\|\s*([^|]+?)\s*\|\s*$"
)

# 4-column reserved table: Label | Family | Planned-for | Notes
_RESERVED_ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|[^|]*\|[^|]*\|[^|]*\|\s*$"
)


def _parse_capability_catalog(
    catalog_path: Path,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Parse `capability-labels.md` and return (all, singular, latent) sets.

    The markdown tables have 5 columns; only column 0 (label, in backticks) and
    column 4 (Type) are extracted. Type values are normalised to lowercase ASCII
    so accented forms (Latente, Auxiliar, Reservada) and English fallbacks
    (Singular, Latent, Auxiliary, Reserved) all map cleanly.

    Reserved tables (under "Labels reservadas v1.1+") have a different shape
    and are matched separately so reserved labels are still recognised as known.
    """
    if not catalog_path.is_file():
        raise CardError(f"capability-labels catalog not found at {catalog_path}")

    text = catalog_path.read_text(encoding="utf-8")

    all_labels: set[str] = set()
    singular: set[str] = set()
    latent: set[str] = set()

    in_reserved_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_reserved_section = "reservadas" in stripped.lower()
            continue
        if not stripped.startswith("|"):
            continue
        if in_reserved_section:
            m = _RESERVED_ROW_RE.match(stripped)
            if m:
                label = m.group(1).strip()
                if label and label != "Label":
                    all_labels.add(label)
            continue
        m = _LABEL_ROW_RE.match(stripped)
        if not m:
            continue
        label, type_token = m.group(1).strip(), m.group(2).strip().lower()
        if not label or label == "Label":
            continue
        all_labels.add(label)
        if type_token.startswith("singular"):
            singular.add(label)
        elif type_token.startswith("latent"):
            latent.add(label)

    if not all_labels:
        raise CardError(
            f"capability-labels catalog {catalog_path} parsed zero labels — "
            "table format may have drifted"
        )

    return frozenset(all_labels), frozenset(singular), frozenset(latent)


# Module-level lazy cache (singleton). Reset by `_reset_catalog_cache` for tests.
_CATALOG_CACHE: dict[str, frozenset[str]] = {}


def _get_catalog() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Return (all_labels, singular_labels, latent_labels), parsing once."""
    if "all" not in _CATALOG_CACHE:
        catalog_path = forge_home() / "docs/schemas/capability-labels.md"
        all_labels, singular, latent = _parse_capability_catalog(catalog_path)
        _CATALOG_CACHE["all"] = all_labels
        _CATALOG_CACHE["singular"] = singular
        _CATALOG_CACHE["latent"] = latent
    return (
        _CATALOG_CACHE["all"],
        _CATALOG_CACHE["singular"],
        _CATALOG_CACHE["latent"],
    )


def _reset_catalog_cache() -> None:
    """Drop the cached catalog. Used by tests and `forge debug` refresh."""
    _CATALOG_CACHE.clear()
    _AGENT_EXT_POINTS_CACHE.clear()


# ── Agent extension-points registry (lazy, parsed from agents/*.md frontmatter)


_AGENT_EXT_POINTS_CACHE: dict[str, dict[str, set[str]]] = {}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)


def _strip_bom(text: str) -> str:
    """F10: remove BOM UTF-8 (`\\ufeff`) caso esteja no início — alguns editores
    Windows (Notepad, VSCode default) emitem BOM em arquivos UTF-8, e a regex
    de frontmatter exige `---` no byte 0.
    """
    return text.lstrip("﻿")


def _load_agent_extension_points(agents_dir: Path) -> dict[str, set[str]]:
    """Walk `agents/*.md`, parse YAML frontmatter, extract extension-points.

    Returns `{agent_name: {extension_point_id, ...}}`. Agents that do not
    declare any `extension-points:` block map to an empty set (so callers can
    still detect "known agent, no extension-points formalised").
    """
    if not agents_dir.is_dir():
        raise CardError(f"agents directory not found at {agents_dir}")

    out: dict[str, set[str]] = {}
    for md in sorted(agents_dir.glob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        text = _strip_bom(text)  # F10: tolera BOM UTF-8 emitido por editores Windows.
        m = _FRONTMATTER_RE.match(text)
        if not m:
            continue
        try:
            front = _yaml_lib.safe_load(m.group(1)) or {}
        except _yaml_lib.YAMLError:
            continue
        if not isinstance(front, dict):
            continue
        name = str(front.get("name") or md.stem)
        ext_points = front.get("extension-points") or []
        ids: set[str] = set()
        if isinstance(ext_points, list):
            for ep in ext_points:
                if isinstance(ep, dict) and isinstance(ep.get("id"), str):
                    ids.add(ep["id"])
        out[name] = ids
    return out


def _get_agent_ext_points() -> dict[str, set[str]]:
    """Lazy accessor with module-level cache."""
    if "_data" not in _AGENT_EXT_POINTS_CACHE:
        agents_dir = forge_home() / "agents"
        _AGENT_EXT_POINTS_CACHE["_data"] = _load_agent_extension_points(agents_dir)
    return _AGENT_EXT_POINTS_CACHE["_data"]


def _known_capability_labels() -> frozenset[str]:
    """Lazy proxy used by validators below."""
    return _get_catalog()[0]


def known_singular_labels() -> frozenset[str]:
    """Public accessor used by `engine.cards.resolver`."""
    return _get_catalog()[1]


def known_latent_labels() -> frozenset[str]:
    """Public accessor — labels provided by the environment."""
    return _get_catalog()[2]


# Backwards-compatible alias: lazy `frozenset`-like view via module __getattr__.
def __getattr__(name: str) -> Any:
    if name == "KNOWN_CAPABILITY_LABELS":
        return _known_capability_labels()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_SEMVER_RE = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


# ── Manifest type ────────────────────────────────────────────────────────────


@dataclass
class CardManifest:
    """Parsed `card.yaml` plus the source directory for relative file lookup.

    `raw` is the full yaml dict (preserved for round-trip / future merger needs).
    `source_path` is the directory containing `card.yaml` (canonical OR snapshot).
    """

    name: str
    version: str
    schema_version: int
    description: str
    category: str
    maturity: str
    provides: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    contributes: dict[str, Any] = field(default_factory=dict)
    detection: dict[str, Any] = field(default_factory=dict)
    config_defaults: dict[str, Any] = field(default_factory=dict)
    documentation: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    source_path: Path = field(default_factory=lambda: Path("."))
    legacy_marker: bool = False
    origin: str = "canon"  # "canon" | "local" — set by load_all_cards cascade


# ── Public API ───────────────────────────────────────────────────────────────


def load_card(card_dir: Path) -> CardManifest:
    """Read `card_dir/card.yaml` into a CardManifest. Raises CardError on any
    schema violation.
    """
    card_yaml = card_dir / "card.yaml"
    if not card_yaml.is_file():
        raise CardError(f"card.yaml not found in {card_dir}")

    try:
        data = read_yaml(card_yaml)
    except YamlIOError as exc:
        raise CardError(str(exc)) from exc

    if not isinstance(data, dict):
        raise CardError(f"{card_yaml}: top-level must be a mapping, got {type(data).__name__}")

    violations = validate_card_yaml(data, card_dir)
    hard = [v for v in violations if "-WARN:" not in v]
    if hard:
        joined = "\n  - ".join(hard)
        raise CardError(f"{card_yaml} failed validation:\n  - {joined}")

    identity = data.get("identity") or {}
    contributes = data.get("contributes") or {}

    return CardManifest(
        name=str(identity.get("name", "")),
        version=str(identity.get("version", "")),
        schema_version=int(data.get("schema-version", 1)),
        description=str(identity.get("description", "")),
        category=str(identity.get("category", "")),
        maturity=str(identity.get("maturity", "")),
        provides=list(data.get("provides") or []),
        requires=list(data.get("requires") or []),
        conflicts_with=list(data.get("conflicts-with") or []),
        contributes=dict(contributes),
        detection=dict(data.get("detection") or {}),
        config_defaults=dict(contributes.get("config-defaults") or {}),
        documentation=dict(data.get("documentation") or {}),
        raw=data,
        source_path=card_dir,
        legacy_marker=bool(data.get("legacy-marker", False)),
        origin="canon",  # default; load_all_cards reassigns based on cascade
    )


def load_all_cards(cards_root: Path) -> list[CardManifest]:
    """Load every card under `cards_root/<name>/card.yaml`.

    Backward-compatible shape: when caller passes the canonical cards/ root
    directly (no `.claude/cards/local/` sibling), returns canon-only. When
    caller passes a project root that has `.claude/cards/local/`, returns
    canon ∪ local with `card.origin` tagged.

    Argument semantics (autodetect):
      - If `cards_root` itself contains `<name>/card.yaml` entries, treat it
        as a canon-only root (legacy callers: snapshot dir, canonical dir).
      - If `cards_root` looks like a project root (contains `.claude/`),
        treat it as cascade-mode: canon snapshot under
        `cards_root/.claude/cards/<name>/` + local under
        `cards_root/.claude/cards/local/<name>/`.

    Raises:
      CardConflictError: when a name appears in both canon and local layers.

    Side-effects (cascade mode only):
      Writes `<project>/.claude/inventory/local-cards-manifest.yaml`
      listing local card names + provides + conflicts-with for CI audit.
    """
    if not cards_root.is_dir():
        raise CardError(f"cards root not found: {cards_root}")

    # Autodetect: if `.claude/` exists at cards_root, treat as project-root cascade.
    project_marker = cards_root / ".claude"
    if project_marker.is_dir() and not (cards_root / "card.yaml").exists():
        return _load_with_cascade(cards_root)

    # Legacy canon-only path: cards_root holds <name>/card.yaml siblings.
    manifests: list[CardManifest] = []
    for entry in sorted(cards_root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if not (entry / "card.yaml").is_file():
            continue
        manifest = load_card(entry)
        manifest.origin = "canon"
        manifests.append(manifest)
    return manifests


def _load_with_cascade(project_root: Path) -> list[CardManifest]:
    """Cascade load: canon snapshot first, local overlay second.

    Order is deliberate — canon is the audited set, local is the controlled
    extension. Inverting order would permit silent override (violates
    Approach A from spec).
    """
    canon_root = project_root / ".claude" / "cards"
    local_root = project_root / ".claude" / "cards" / "local"

    canon: dict[str, CardManifest] = {}
    if canon_root.is_dir():
        for entry in sorted(canon_root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue  # skips `.archived/`, `.git/`, etc.
            if entry.name == "local":
                continue  # the overlay dir is handled below, not a canon card
            if not (entry / "card.yaml").is_file():
                continue
            manifest = load_card(entry)
            manifest.origin = "canon"
            canon[manifest.name] = manifest

    local: dict[str, CardManifest] = {}
    if local_root.is_dir():
        for entry in sorted(local_root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            if not (entry / "card.yaml").is_file():
                # Empty local card dir: warning skip. Caller (forge doctor)
                # can surface; loader stays quiet to keep snapshot loadable.
                continue
            manifest = load_card(entry)
            manifest.origin = "local"
            local[manifest.name] = manifest

    # Hard fail on name collision — Approach A.
    conflicts = sorted(set(canon) & set(local))
    if conflicts:
        raise CardConflictError(
            f"Nomes em colisão canon×local: {conflicts}. "
            f"Renomeie o card local ou abra ADR pra promoção ao canon."
        )

    # Manifest write side-effect (cascade mode only).
    _write_local_cards_manifest(project_root, local)

    return [canon[name] for name in sorted(canon)] + [
        local[name] for name in sorted(local)
    ]


def validate_card_yaml(manifest_dict: dict[str, Any], source_path: Path) -> list[str]:
    """Validate a parsed `card.yaml` dict against CARD-001..CARD-018.

    Returns a list of violation strings. Empty list = card is valid.
    Implements the static checks only — cross-card validation (CARD-007/008/017)
    lives in the resolver.
    """
    violations: list[str] = []

    schema_version = manifest_dict.get("schema-version")
    if schema_version != 1:
        violations.append(
            f"CARD-001: schema-version must be 1, got {schema_version!r}"
        )

    identity = manifest_dict.get("identity") or {}
    if not isinstance(identity, dict):
        violations.append("CARD-001: `identity` block missing or not a mapping")
        identity = {}

    name = identity.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        violations.append(
            f"CARD-002: identity.name must match [a-z0-9-]+ (≤40 chars), got {name!r}"
        )

    version = identity.get("version")
    if not isinstance(version, str) or not _SEMVER_RE.match(version):
        violations.append(
            f"CARD-003: identity.version must be valid semver, got {version!r}"
        )

    category = identity.get("category")
    if category not in _KNOWN_CATEGORIES:
        violations.append(
            f"CARD-004: identity.category must be one of {sorted(_KNOWN_CATEGORIES)}, "
            f"got {category!r}"
        )

    maturity = identity.get("maturity")
    if maturity not in _KNOWN_MATURITIES:
        violations.append(
            f"CARD-005: identity.maturity must be one of {sorted(_KNOWN_MATURITIES)}, "
            f"got {maturity!r}"
        )

    provides = manifest_dict.get("provides")
    if not isinstance(provides, list) or len(provides) == 0:
        violations.append("CARD-006: provides must be a non-empty list")
    else:
        for label in provides:
            if not isinstance(label, str):
                violations.append(f"CARD-006: provides entry must be string, got {label!r}")
                continue
            if label not in _known_capability_labels():
                violations.append(
                    f"CARD-006: provides label {label!r} not in canonical catalog"
                )

    requires = manifest_dict.get("requires") or []
    if not isinstance(requires, list):
        violations.append("CARD-007: requires must be a list (possibly empty)")
    else:
        for label in requires:
            if not isinstance(label, str):
                violations.append(f"CARD-007: requires entry must be string, got {label!r}")
                continue
            if label not in _known_capability_labels():
                violations.append(
                    f"CARD-007: requires label {label!r} not in canonical catalog"
                )

    conflicts = manifest_dict.get("conflicts-with") or []
    if not isinstance(conflicts, list):
        violations.append("CARD-008: conflicts-with must be a list (possibly empty)")
    else:
        # CARD-008 — entries may be capability labels OR card names. Card names
        # are validated cross-card by the resolver; here we only check shape.
        for entry in conflicts:
            if not isinstance(entry, str) or not entry:
                violations.append(f"CARD-008: conflicts-with entry must be non-empty string, got {entry!r}")

    contributes = manifest_dict.get("contributes") or {}
    if not isinstance(contributes, dict):
        violations.append("CARD-009: contributes must be a mapping when present")
        contributes = {}

    _validate_templates(contributes.get("templates"), violations)
    _validate_validators(contributes.get("validators"), source_path, violations)
    _validate_agent_prompts(contributes.get("agent-prompts"), violations)
    _validate_hooks(contributes.get("hooks"), violations)
    _validate_config_defaults(contributes.get("config-defaults"), violations)

    detection = manifest_dict.get("detection") or {}
    if not isinstance(detection, dict):
        violations.append("CARD-015: detection must be a mapping when present")
    else:
        threshold = detection.get("threshold")
        if threshold is not None and not (
            isinstance(threshold, (int, float)) and 0.0 <= float(threshold) <= 1.0
        ):
            violations.append(
                f"CARD-015: detection.threshold must be in [0.0, 1.0], got {threshold!r}"
            )

        signals = detection.get("signals") or []
        if not isinstance(signals, list):
            violations.append("CARD-016: detection.signals must be a list")
        else:
            confidence_sum = 0.0
            for sig in signals:
                if not isinstance(sig, dict):
                    continue
                conf = sig.get("confidence")
                if isinstance(conf, (int, float)):
                    confidence_sum += float(conf)
            # CARD-016 hard-fail: confidence_sum > 2.0 indica detection over-stacked.
            # Cards reais devem manter sinais ortogonais — somar > 2.0 sinaliza
            # heurísticas redundantes ou inflação de confiança.
            if confidence_sum > 2.0:
                violations.append(
                    f"CARD-016 violation: confidence sum {confidence_sum:.2f} > 2.0"
                )

    readme = source_path / "README.md"
    if not readme.is_file():
        violations.append(f"CARD-018: README.md must exist at {readme}")

    return violations


# ── Private helpers ──────────────────────────────────────────────────────────


def _validate_templates(templates: Any, violations: list[str]) -> None:
    if templates is None:
        return
    if not isinstance(templates, list):
        violations.append("CARD-009: contributes.templates must be a list")
        return
    for t in templates:
        if not isinstance(t, dict):
            violations.append(f"CARD-009: template entry must be mapping, got {t!r}")
            continue
        target = t.get("target")
        if not isinstance(target, str) or not target:
            violations.append("CARD-009: template.target must be a non-empty string")
        merge = t.get("merge")
        if merge is not None and merge not in _KNOWN_MERGE_MODES:
            violations.append(
                f"CARD-009: template.merge must be one of {sorted(_KNOWN_MERGE_MODES)}, "
                f"got {merge!r}"
            )


def _validate_validators(validators: Any, source_path: Path, violations: list[str]) -> None:
    if validators is None:
        return
    if not isinstance(validators, list):
        violations.append("CARD-010: contributes.validators must be a list")
        return
    for v in validators:
        if not isinstance(v, dict):
            violations.append(f"CARD-010: validator entry must be mapping, got {v!r}")
            continue
        name = v.get("name")
        if not isinstance(name, str) or not name:
            violations.append("CARD-010: validator.name must be a non-empty string")
        file_ref = v.get("file")
        if not isinstance(file_ref, str) or not file_ref:
            violations.append("CARD-010: validator.file must be a string")
        else:
            target = (source_path / file_ref).resolve()
            if not target.is_file():
                # CARD-010 requires file to exist; allow stub-mode warn (not error).
                # We surface as violation since loader is strict — callers may
                # downgrade if they accept stubs.
                violations.append(
                    f"CARD-010: validator file {file_ref!r} not found at {target}"
                )
        runs_on = v.get("runs-on") or []
        if not isinstance(runs_on, list):
            violations.append("CARD-010: validator.runs-on must be a list")
        else:
            for event in runs_on:
                if event not in _KNOWN_RUNS_ON:
                    violations.append(
                        f"CARD-010: validator.runs-on entry {event!r} not in "
                        f"{sorted(_KNOWN_RUNS_ON)}"
                    )
        severity = v.get("severity")
        if severity is not None and severity not in _KNOWN_SEVERITIES:
            violations.append(
                f"CARD-010: validator.severity must be one of {sorted(_KNOWN_SEVERITIES)}, "
                f"got {severity!r}"
            )


def _validate_agent_prompts(prompts: Any, violations: list[str]) -> None:
    if prompts is None:
        return
    if not isinstance(prompts, list):
        violations.append("CARD-011: contributes.agent-prompts must be a list")
        return

    # Cross-check registry: agents/*.md frontmatter `extension-points`.
    try:
        registry = _get_agent_ext_points()
    except CardError:
        registry = {}

    for p in prompts:
        if not isinstance(p, dict):
            violations.append(f"CARD-011: agent-prompt entry must be mapping, got {p!r}")
            continue
        inject_into = p.get("inject-into")
        if not isinstance(inject_into, str) or not inject_into:
            violations.append("CARD-011: agent-prompt.inject-into must be a non-empty string")
            continue
        if registry and inject_into not in registry:
            violations.append(
                f"CARD-011: agent-prompt.inject-into {inject_into!r} does not match "
                f"any agent in agents/ (known: {sorted(registry)})"
            )

        ext_point = p.get("extension-point")
        if not isinstance(ext_point, str) or not ext_point:
            violations.append("CARD-012: agent-prompt.extension-point must be a non-empty string")
            continue
        # CARD-012 — if the agent declares extension-points, the id MUST exist
        # there. Agents without a formal extension-points block emit a warning
        # only (some agents have not formalised theirs yet — FOLLOWUP historic).
        declared = registry.get(inject_into)
        if declared is None:
            continue
        if not declared:
            violations.append(
                f"CARD-012-WARN: agent {inject_into!r} declares no extension-points "
                f"in its frontmatter — cannot verify {ext_point!r}"
            )
        elif ext_point not in declared:
            violations.append(
                f"CARD-012: extension-point {ext_point!r} not declared by agent "
                f"{inject_into!r} (known: {sorted(declared)})"
            )


def _validate_hooks(hooks: Any, violations: list[str]) -> None:
    if hooks is None:
        return
    if not isinstance(hooks, list):
        violations.append("CARD-013: contributes.hooks must be a list")
        return
    for h in hooks:
        if not isinstance(h, dict):
            violations.append(f"CARD-013: hook entry must be mapping, got {h!r}")
            continue
        events = h.get("events") or []
        if not isinstance(events, list):
            violations.append("CARD-013: hook.events must be a list")
            continue
        for event in events:
            if event not in _KNOWN_HOOK_EVENTS:
                violations.append(
                    f"CARD-013: hook.events entry {event!r} not in {sorted(_KNOWN_HOOK_EVENTS)}"
                )


def _validate_config_defaults(defaults: Any, violations: list[str]) -> None:
    if defaults is None:
        return
    if not isinstance(defaults, dict):
        violations.append("CARD-014: contributes.config-defaults must be a mapping")
        return
    for key in defaults:
        if not isinstance(key, str) or not key:
            violations.append(f"CARD-014: config-defaults key must be non-empty string, got {key!r}")


def _write_local_cards_manifest(
    project_root: Path, local: dict[str, "CardManifest"]
) -> None:
    """Write `.claude/inventory/local-cards-manifest.yaml` for CI audit.

    Stub in Task 4 — fully implemented in Task 5. Stub no-op when local is
    empty (canon-only project = no manifest needed).
    """
    if not local:
        return
    # Task 5 expands this to write the YAML. Leave as no-op here.
    return
