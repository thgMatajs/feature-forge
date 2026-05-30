#!/usr/bin/env python3
"""validate_data_contract.py — Data contract schema check (Fase 3.5+).

Validates `data-contract-spec.yaml` against the schema in
`templates/data-contract-spec.template.yaml`:

- schema_version == 1
- persistence_strategy ∈ {firebase-firestore, rest-api, mixed, local-only, none}
- entities is a non-empty list; each entity has name + fields + data_origins
- persistence_strategy is consistent with active cards (e.g.,
  `firebase-firestore` requires a firestore-* card active)
- if ANY entity has data_origins.api.exists==true, top-level `backend_e2e`
  block must be present and non-empty (template rule).

Schema source: templates/data-contract-spec.template.yaml.
"""

from __future__ import annotations

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

from engine.utils.paths import feature_dir, workflow_config_path  # noqa: E402
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402


_VALID_PERSISTENCE_STRATEGIES = {
    "firebase-firestore",
    "rest-api",
    "mixed",
    "local-only",
    "none",
}

# Which cards satisfy each persistence_strategy. Validator warns if strategy
# is declared but no satisfying card is active.
_STRATEGY_CARD_HINTS: dict[str, set[str]] = {
    "firebase-firestore": {"firestore-persistence", "firestore-realtime"},
    "rest-api": {"rest-api-contract", "ktor-client"},
    "local-only": {"room-database", "datastore-prefs"},
    "mixed": set(),  # any combination
    "none": set(),
}


def _resolve_slug(kwargs: dict[str, Any]) -> str | None:
    scope = kwargs.get("scope") or "inferred"
    given_id = kwargs.get("id")
    if scope == "feature" and given_id:
        return given_id
    if given_id and not given_id.upper().startswith("TASK-"):
        return given_id
    return None


def _active_card_names(config: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for entry in (config.get("cards") or {}).get("active") or []:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            out.add(entry["name"])
    return out


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate the data-contract-spec.yaml for the active feature."""
    slug = _resolve_slug(kwargs)
    if not slug:
        return result_warn(
            "no feature slug provided — data-contract check skipped",
            what_failed="no slug",
            where="--scope feature --id <slug>",
            why=["data-contract is per-feature"],
        )

    f_root = feature_dir(project_root, slug)
    contract = f_root / "data-contract-spec.yaml"
    if not contract.is_file():
        return result_warn(
            f"data-contract-spec.yaml ausente em {slug}/",
            what_failed="missing data-contract-spec.yaml",
            where=str(contract.relative_to(project_root)),
            why=["Wave B (contract-planner) ainda não rodou ou strictness=lean"],
        )

    try:
        data = read_yaml_or_default(contract, {}) or {}
    except Exception as exc:  # noqa: BLE001
        return result_fail(
            "data-contract-spec.yaml inválido (YAML parse error)",
            what_failed=str(exc),
            where=str(contract.relative_to(project_root)),
            why=["Sub-agents downstream parsing falha"],
            paths=make_paths(
                "Corrigir o YAML manualmente — checar indentação/quotes",
                "Erros YAML costumam ser tabs ou aspas misturadas.",
                "Reverter o último edit — `forge undo`",
                "Se a corrupção é recente.",
                "Re-gerar via `forge plan <slug> --rerun=data-contract`",
                "Se o sub-agent escreveu o YAML errado.",
            ),
        )

    violations: list[str] = []
    if data.get("schema_version") != 1:
        violations.append(f"schema_version must be 1, got {data.get('schema_version')!r}")

    strategy = data.get("persistence_strategy")
    if strategy not in _VALID_PERSISTENCE_STRATEGIES:
        violations.append(
            f"persistence_strategy must be in {sorted(_VALID_PERSISTENCE_STRATEGIES)}, got {strategy!r}"
        )

    entities = data.get("entities")
    if not isinstance(entities, list) or len(entities) == 0:
        violations.append("entities must be a non-empty list")
    else:
        for idx, entity in enumerate(entities):
            if not isinstance(entity, dict):
                violations.append(f"entities[{idx}] must be a mapping")
                continue
            if not isinstance(entity.get("name"), str) or not entity["name"]:
                violations.append(f"entities[{idx}].name must be non-empty string")
            if "fields" in entity and not isinstance(entity["fields"], list):
                violations.append(f"entities[{idx}].fields must be a list")

    any_api = False
    if isinstance(entities, list):
        for e in entities:
            if not isinstance(e, dict):
                continue
            origins = e.get("data_origins") or {}
            api = (origins or {}).get("api") if isinstance(origins, dict) else None
            if isinstance(api, dict) and api.get("exists") is True:
                any_api = True
                break

    if any_api:
        be2e = data.get("backend_e2e")
        if not isinstance(be2e, dict) or not be2e:
            violations.append(
                "any entity with data_origins.api.exists==true requires top-level backend_e2e block"
            )

    if violations:
        return result_fail(
            f"data-contract-spec.yaml com {len(violations)} violação(ões) de schema",
            what_failed="; ".join(violations[:3]),
            where=str(contract.relative_to(project_root)),
            why=[
                "Template data-contract-spec é AGNÓSTICO de backend mas tem schema fixo.",
                "tech-spec-agent + validate_backend_e2e dependem desse shape.",
            ],
            paths=make_paths(
                "Editar o YAML e corrigir os campos listados",
                "Cada violation aponta o caminho exato.",
                "Re-rodar contract-planner — `forge plan <slug> --rerun=data-contract`",
                "Quando o sub-agent gerou shape incorreto.",
                "Reverter Wave B — `forge undo last-plan-checkpoint`",
                "Se Wave A precisa de ajuste antes.",
            ),
        )

    config = read_yaml_or_default(workflow_config_path(project_root), {}) or {}
    active_cards = _active_card_names(config)
    hint = _STRATEGY_CARD_HINTS.get(strategy, set())
    if hint and not (hint & active_cards):
        return result_warn(
            f"persistence_strategy={strategy} mas nenhum card relacionado está ativo",
            what_failed=f"esperado ao menos um de {sorted(hint)}",
            where=str(contract.relative_to(project_root)),
            why=[
                f"strategy {strategy} requer card de persistência no workflow-config",
                "tech-spec não terá fonte de DTO/Repository sem o card",
            ],
        )

    return result_pass(
        f"data-contract OK (strategy={strategy}, entities={len(entities or [])})"
    )


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
