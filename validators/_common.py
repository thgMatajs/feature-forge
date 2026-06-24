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


# ── Backend axes / platforms — shared validator constants ───────────────────
#
# PR #13 review #3405255016. Antes, `VALID_AXES` (validate_presets) e
# `_VALID_BACKEND_AXES` (validate_forge_config) coexistiam com o mesmo
# conteúdo. Os dois sets de "platforms" eram homônimos mas semanticamente
# distintos:
#
#   · bundle slot keys (presets): {android, ios, kmp, all-platforms}
#   · workflow active platforms:   {android, ios, kmp, web}
#
# Consolidação aqui mantém os dois sets visíveis com nomes
# desambiguados. Os 8 axes são fonte canônica via
# `engine.detection._axes.BACKEND_AXES` mas re-exportar como `frozenset`
# pros validators evita acoplamento direto da camada validators ao módulo
# engine.detection (validators é layer superior na arquitetura).

# 8 axes canônicos — espelha `engine.detection._axes.BACKEND_AXES` com
# `frozenset` shape pra ergonomia de membership checks nos validators.
# Fonte: docs/schemas/backend-axes.md §"Os 8 axes canônicos".
VALID_BACKEND_AXES: frozenset[str] = frozenset(
    {
        "data",
        "auth",
        "observability",
        "analytics",
        "storage",
        "persistence",
        "notifications",
        "flags",
    }
)

# Bundle slot keys (validate_presets) — `all-platforms` é shorthand que
# expande pras 3 plataformas declaradas no bundle (android+ios+kmp).
VALID_BUNDLE_PLATFORM_KEYS: frozenset[str] = frozenset(
    {"android", "ios", "kmp", "all-platforms"}
)

# Workflow active platforms (validate_forge_config) — universo de
# plataformas que um projeto declara em `platforms.active`. `web` entra
# pra cobrir mono-plataforma sem mobile.
VALID_PROJECT_PLATFORMS: frozenset[str] = frozenset(
    {"android", "ios", "kmp", "web"}
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
    # allow_abbrev=False (defense-in-depth, review pr27 C1): sem isso, argparse
    # honra abreviações (--p, --proj, --project, --project-roo) como
    # --project-root. Um vetor que escapasse o allowlist do sandbox poderia
    # re-setar project_root via abreviação (last-wins) e escapar o sandbox
    # (Decisão 30). Desligar abreviação project-wide fecha a classe inteira.
    p = argparse.ArgumentParser(description=description, allow_abbrev=False)
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
    except (OSError, _yaml_lib.YAMLError) as exc:
        # C11/C17: antes só YAMLError era capturado. OSError (permissão,
        # disco corrompido) escapava como traceback bruto. Wrap em
        # CatalogOverlayError pra mensagem mentor calmo + path/cause.
        raise CatalogOverlayError(
            f"{local_path}: erro ao ler ou processar arquivo — {exc}"
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


# ── Gate helpers (threshold lookup + 3-paths render) ─────────────────────────
#
# Usados hoje por `validators/check_cyclomatic_complexity.py`. Vivem em
# _common pra serem testáveis isoladamente e pra deixar o validator principal
# mais enxuto. Sem I/O — pura lookup + string formatting. Outros gates
# (planejado: secrets, etc.) reusam mesma forma.

DEFAULTS_CC: dict[str, int] = {
    "kotlin": 10,
    "swift": 10,
    "ts": 15,
    "python": 10,
}


def gate_threshold_lookup(
    language: str,
    active_cards: list[dict[str, Any]],
    workflow_config: dict[str, Any],
    *,
    card_override_key: str = "cc-gate-override",
    workflow_block_key: str = "cc-gate",
    defaults: dict[str, int] | None = None,
) -> int:
    """Resolve gate threshold for a language (gate-agnóstico via kwargs).

    Precedence: card[card_override_key] > workflow_config[workflow_block_key]
    > defaults.

    Sem kwargs custom, comportamento idêntico ao CC gate original:
        card "cc-gate-override" > workflow-config "cc-gate" > DEFAULTS_CC.

    Multiple cards conflicting: first card with a `threshold` key wins
    (deterministic, matches declaration order). Card override entries
    without an explicit `threshold` field fall through to the next layer.

    Args:
        language: Language name (matches keys em defaults).
        active_cards: Lista de cards ativos (dicts).
        workflow_config: Workflow config dict.
        card_override_key: Chave de override no card.yaml (default
            "cc-gate-override"). Outros gates: "cog-gate-override",
            "func-length-override", etc.
        workflow_block_key: Chave do block no workflow-config.yaml
            (default "cc-gate"). Outros gates: "cog-gate", etc.
        defaults: Tabela de defaults por linguagem (default DEFAULTS_CC).

    Note:
        Threshold ≤ 0 (configuração degenerada) é repassado raw pro caller.
        Helper é dumb-lookup; semântica "degraded" fica no validator caller
        (check_cyclomatic_complexity.validate() e equivalentes).
    """
    effective_defaults = defaults if defaults is not None else DEFAULTS_CC
    for card in active_cards:
        if not isinstance(card, dict):
            continue
        override = card.get(card_override_key) or {}
        if not isinstance(override, dict):
            continue
        lang_block = override.get(language)
        if not isinstance(lang_block, dict):
            continue
        if "threshold" in lang_block:
            try:
                return int(lang_block["threshold"])
            except (TypeError, ValueError):
                continue

    cfg_block = workflow_config.get(workflow_block_key) or {}
    if isinstance(cfg_block, dict) and language in cfg_block:
        try:
            return int(cfg_block[language])
        except (TypeError, ValueError):
            pass

    if language not in effective_defaults:
        raise ValueError(
            f"language {language!r} not in gate scope; "
            f"supported: {sorted(effective_defaults)}"
        )
    return effective_defaults[language]


_DEFAULT_CC_WHY_LINES = (
    "Funções com CC alto são mais difíceis de testar, revisar e evoluir.",
)

_DEFAULT_CC_OVERRIDE_EXAMPLE = (
    "CC-OVERRIDE: <file>:<func> cc=<N> — <razão concreta>"
)


def format_three_paths_message(
    violations: list[dict[str, Any]],
    thresholds: dict[str, int],
    *,
    gate_title: str = "🛑 Cyclomatic Complexity gate",
    why_lines: list[str] | tuple[str, ...] | None = None,
    override_example: str = _DEFAULT_CC_OVERRIDE_EXAMPLE,
    format_annotation: Callable[[dict[str, Any]], str] | None = None,
) -> str:
    """Render the canonical 3-paths message (gate-agnóstico via kwargs).

    Sem kwargs custom, snapshot CC gate preservado byte-a-byte. Outros gates
    numéricos (Cognitive Complexity, Function Length, etc.) sobrescrevem
    `gate_title` / `why_lines` / `override_example` / `format_annotation`
    pra vocabulário próprio.

    Args:
        violations: Lista de dicts (file, line, function, cc, threshold,
            status, cc_before, language).
        thresholds: Threshold vigente por linguagem.
        gate_title: Cabeçalho do gate (default CC).
        why_lines: Lista de bullets "Por que importa". `None` usa default CC.
        override_example: Linha-modelo do override-justify.
        format_annotation: Callable opcional `(violation_dict) -> str` que
            customiza a annotation per-row (default: CC-specific
            "[new]" / "↑ de cc=N [modified]"). Permite outros gates terem
            anotação própria sem reescrever todo o render.

    Snapshot in tests — keep wording stable. See
    `.claude/rules/disciplines.md §1` for the template contract.
    """
    if not violations:
        raise ValueError(
            "format_three_paths_message requires at least one violation"
        )
    effective_why = list(why_lines) if why_lines is not None else list(_DEFAULT_CC_WHY_LINES)
    annotate = format_annotation if format_annotation is not None else _default_cc_annotation
    lines: list[str] = []
    lines.append(gate_title)
    lines.append("")
    lines.append("O que falhou:")
    lines.append(f"  {len(violations)} funções excederam o threshold permitido.")
    lines.append("")
    lines.append("Onde:")
    for v in violations:
        annotation = annotate(v)
        lines.append(
            f"  · {v['file']}:{v['line']} — {v['function']}()"
            f"        cc={v['cc']}  (limite: {v['threshold']}){annotation}"
        )
    lines.append("")
    lines.append("Por que importa:")
    for why in effective_why:
        lines.append(f"  · {why}")
    th_str = ", ".join(f"{lang}={n}" for lang, n in sorted(thresholds.items()))
    lines.append(f"  · Threshold vigente: {th_str} (workflow-config.yaml)")
    lines.append("  · Decision 23 — cascade fail-fast; CC é gate hard.")
    lines.append("")
    lines.append("Três caminhos pra resolver:")
    lines.append("")
    lines.append("  1) Refatorar")
    lines.append(
        "     Quebra a função em helpers menores. Tipicamente: extrair branches"
    )
    lines.append(
        "     condicionais, validações, ou loops em métodos privados nomeados."
    )
    lines.append("     Re-rodar `forge verify` confirma.")
    lines.append("")
    lines.append("  2) Override-justify (commit body)")
    lines.append(
        "     Se a complexidade é genuinamente irredutível (state machine, parser,"
    )
    lines.append(
        "     DSL), adicionar ao commit body — EXATAMENTE este formato:"
    )
    lines.append("")
    lines.append(f"         {override_example}")
    lines.append("")
    lines.append(
        "     Validator detecta a linha no commit body e libera APENAS este commit."
    )
    lines.append(
        "     Auditável via `git log --grep='CC-OVERRIDE'`. NÃO é whitelist persistente."
    )
    lines.append("")
    lines.append("  3) Split-task")
    lines.append(
        "     Dividir a task atual em sub-tasks menores. Tipicamente o sintoma é"
    )
    lines.append(
        "     \"task fez coisa demais\" — split via `forge implement` reabrindo"
    )
    lines.append("     task-breakdown.")
    lines.append("")
    lines.append("Sem auto-fix aqui — escolha humana.")
    return "\n".join(lines)


def _default_cc_annotation(v: dict[str, Any]) -> str:
    """Annotation per-row do CC gate — preserva snapshot byte-a-byte."""
    if v.get("status") == "new":
        return " [new]"
    if v.get("status") == "modified" and v.get("cc_before") is not None:
        return f"  ↑ de cc={v['cc_before']} [modified]"
    return ""
