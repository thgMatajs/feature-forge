#!/usr/bin/env python3
"""validate_backend_e2e.py — Backend E2E test strategy check.

When `data-contract-spec.yaml` has any entity with `data_origins.api.exists ==
true`, the feature MUST declare a backend_e2e block in `test-strategy.yaml`:

- enabled == true
- provider declared and matches one of the active backend-related cards
- cli.run is non-empty
- scenarios_covered references BE2E-NNN ids present in
  `data-contract-spec.backend_e2e.scenarios`

Schema sources: templates/test-strategy.template.yaml §backend_e2e +
templates/data-contract-spec.template.yaml.
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


_PROVIDER_TO_CARD: dict[str, set[str]] = {
    "firestore_emulator": {"firestore-persistence", "firestore-realtime"},
    "mock_server_rest": {"rest-api-contract", "ktor-client"},
    "contract_tests": {"rest-api-contract"},
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


def _has_api_origin(data_contract: dict[str, Any]) -> bool:
    for e in data_contract.get("entities") or []:
        if not isinstance(e, dict):
            continue
        origins = e.get("data_origins") or {}
        api = origins.get("api") if isinstance(origins, dict) else None
        if isinstance(api, dict) and api.get("exists") is True:
            return True
    return False


def _backend_e2e_scenarios_in_contract(data_contract: dict[str, Any]) -> set[str]:
    be2e = data_contract.get("backend_e2e") or {}
    if not isinstance(be2e, dict):
        return set()
    scenarios = be2e.get("scenarios") or []
    out: set[str] = set()
    for sc in scenarios:
        if isinstance(sc, dict) and isinstance(sc.get("id"), str):
            out.add(sc["id"])
        elif isinstance(sc, str):
            out.add(sc)
    return out


def _active_cards(config: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for entry in (config.get("cards") or {}).get("active") or []:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            out.add(entry["name"])
    return out


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate backend_e2e wiring between data-contract and test-strategy."""
    slug = _resolve_slug(kwargs)
    if not slug:
        return result_warn(
            "no feature slug provided — backend_e2e check skipped",
            what_failed="no slug",
            where="--scope feature --id <slug>",
            why=["backend_e2e is per-feature"],
        )

    f_root = feature_dir(project_root, slug)
    data_path = f_root / "data-contract-spec.yaml"
    strat_path = f_root / "test-strategy.yaml"

    if not data_path.is_file() or not strat_path.is_file():
        return result_warn(
            "data-contract-spec.yaml ou test-strategy.yaml ausente",
            what_failed=f"need both files in {f_root.name}/",
            where=str(f_root.relative_to(project_root)),
            why=["lean/standard strictness pode omitir esses artefatos"],
        )

    try:
        data_contract = read_yaml_or_default(data_path, {}) or {}
        test_strategy = read_yaml_or_default(strat_path, {}) or {}
    except Exception as exc:  # noqa: BLE001
        return result_fail(
            "YAML parse error em data-contract ou test-strategy",
            what_failed=str(exc),
            where=str(f_root.relative_to(project_root)),
            why=["Sub-agents downstream parsing falha"],
            paths=make_paths(
                "Corrigir o YAML manualmente",
                "Tipicamente indentação ou aspas.",
                "Reverter o último edit — `forge undo`",
                "Se a corrupção é recente.",
                "Re-gerar — `forge plan <slug> --rerun=<artifact>`",
                "Se o sub-agent quebrou o shape.",
            ),
        )

    if not _has_api_origin(data_contract):
        return result_pass(
            "data-contract sem entity com data_origins.api.exists==true — backend_e2e opcional"
        )

    be2e = test_strategy.get("backend_e2e") or {}
    if not isinstance(be2e, dict) or not be2e.get("enabled"):
        return result_fail(
            "data-contract requer backend_e2e mas test-strategy.backend_e2e.enabled != true",
            what_failed=f"backend_e2e.enabled={be2e.get('enabled')!r}",
            where=str(strat_path.relative_to(project_root)),
            why=[
                "Template (test-strategy §backend_e2e) exige enabled=true quando há entity com api.",
                "Hard rule: backend_e2e.scenarios_covered referencia BE2E-NNN do data-contract.",
            ],
            paths=make_paths(
                "Setar backend_e2e.enabled=true e preencher provider+cli+scenarios_covered",
                "Cli pode ser firebase emulator ou mock-server start/run/teardown.",
                "Remover entity com api.exists=true do data-contract",
                "Se a feature na verdade é local-only.",
                "Re-gerar contracts — `forge plan <slug> --rerun=contracts`",
                "Quando os artefatos divergem entre si por bug de sub-agent.",
            ),
        )

    violations: list[str] = []
    provider = be2e.get("provider")
    if not isinstance(provider, str) or not provider or "{{" in provider:
        violations.append("provider não declarado em test-strategy.backend_e2e.provider")

    cli = be2e.get("cli") or {}
    run_cmd = cli.get("run") if isinstance(cli, dict) else None
    if not isinstance(run_cmd, str) or not run_cmd or "{{" in run_cmd:
        violations.append("test-strategy.backend_e2e.cli.run vazio ou template placeholder")

    contract_scenarios = _backend_e2e_scenarios_in_contract(data_contract)
    covered = set(be2e.get("scenarios_covered") or [])
    missing_coverage = contract_scenarios - covered
    if contract_scenarios and missing_coverage:
        violations.append(
            f"scenarios_covered não cobre {sorted(missing_coverage)} declarados no data-contract"
        )

    # Cross-check provider vs active cards (warn-level if no card matches)
    config = read_yaml_or_default(workflow_config_path(project_root), {}) or {}
    cards = _active_cards(config)
    hint = _PROVIDER_TO_CARD.get(str(provider), set())
    if provider and hint and not (hint & cards):
        violations.append(
            f"provider={provider} mas nenhum card relacionado ({sorted(hint)}) ativo"
        )

    if violations:
        return result_fail(
            f"backend_e2e com {len(violations)} violação(ões)",
            what_failed="; ".join(violations[:3]),
            where=str(strat_path.relative_to(project_root)),
            why=[
                "test-strategy.backend_e2e é o contrato pra rodar e2e CI.",
                "Sem cli.run + scenarios_covered, validate_backend_e2e em CI quebra build.",
            ],
            paths=make_paths(
                "Editar test-strategy.yaml e preencher cli + scenarios_covered",
                "Os ids BE2E-NNN vêm do data-contract-spec.yaml.",
                "Re-gerar — `forge plan <slug> --rerun=test-strategy`",
                "Quando o sub-agent não preencheu cli.run.",
                "Reverter contracts — `forge undo last-plan-checkpoint`",
                "Se Wave B inteira está inconsistente.",
            ),
        )

    return result_pass(
        f"backend_e2e OK (provider={provider}, scenarios={len(covered)})"
    )


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
