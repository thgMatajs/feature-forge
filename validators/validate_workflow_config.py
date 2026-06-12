#!/usr/bin/env python3
"""validate_workflow_config.py — workflow-config.yaml schema + sha256 integrity.

Validates `.claude/workflow-config.yaml`:
- schema-version == 1 (RULE-001)
- required top-level blocks present (identity, platforms, cards, paths,
  conventions, backend, workflow, persona, memory, graph)
- identity.project-slug matches [a-z0-9-]+ (RULE-002)
- platforms.active ⊆ {android, ios, kmp, web} (RULE-004)
- cards.active sha256 still matches the on-disk snapshot (RULE-006)
- paths.feature-roots existem no disco (RULE-008, soft warn)
- backend cell structure (multi-axis) — RULE-019..024 (DET-6 / W7.4):
    · RULE-019  axis ∈ enum canônico (data, auth, observability, …)
    · RULE-020  platform ∈ platforms.active OR é null cell
    · RULE-021  cell.card referencia card existente em cards/
    · RULE-022  cell.status ∈ {active, migrating-to, deprecated}
    · RULE-023  cell.migrating-to consistency com status
    · RULE-024  cell.migrating-to referencia card existente em cards/
- workflow.readiness-strictness ∈ {strict, standard, lean} (RULE-013)
- L1 mutation lock — operations bloqueadas se algum L1 está em phase ativa (RULE-018)

Schema source: docs/schemas/workflow-config.md (RULE-001..018) +
docs/schemas/backend-axes.md (RULE-019..024). DET-6 Phase B removeu
RULE-010/011 (legacy `backend.provider`) — esses slots ficam reservados
como audit-trail do clean-break pre-production.

RULEs ainda não cobertas: RULE-003, 005, 007, 009, 012, 014, 015, 016, 017
(# TODO Phase 6 — exigem cruzar com presets/persona/hooks externos).
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

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.utils.paths import cards_dir, memory_dir, workflow_config_path  # noqa: E402
from engine.utils.sha256 import file_sha256  # noqa: E402
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402

_REQUIRED_TOP_LEVEL = (
    "schema-version",
    "identity",
    "platforms",
    "cards",
    "paths",
    "conventions",
    "backend",
    "workflow",
    "persona",
    "memory",
    "graph",
)

_VALID_PLATFORMS = {"android", "ios", "kmp", "web"}
_VALID_STRICTNESS = {"strict", "standard", "lean"}
# DET-6 / W7.4 — backend multi-axis (substitui RULE-010/011 monolíticos).
_VALID_BACKEND_AXES = {
    "data",
    "auth",
    "observability",
    "analytics",
    "storage",
    "persistence",
    "notifications",
    "flags",
}
_VALID_CELL_STATUSES = {"active", "migrating-to", "deprecated"}
_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
# Estados L1 que indicam fase ativa (mutation forbidden via RULE-018).
_L1_ACTIVE_STATES = {"planning", "implementing", "verifying"}


def _check_required(data: dict[str, Any]) -> list[str]:
    return [k for k in _REQUIRED_TOP_LEVEL if k not in data]


def _check_project_slug(data: dict[str, Any]) -> list[str]:
    """RULE-002: identity.project-slug must match [a-z0-9-]+ regex."""
    identity = data.get("identity") if isinstance(data, dict) else None
    if not isinstance(identity, dict):
        return []
    slug = identity.get("project-slug")
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        return [f"identity.project-slug {slug!r} não casa com regex [a-z0-9-]+ (RULE-002)"]
    return []


def _check_platforms_active(data: dict[str, Any]) -> list[str]:
    """RULE-004: platforms.active não-vazio + ⊆ {android, ios, kmp, web}."""
    platforms = data.get("platforms") if isinstance(data, dict) else None
    if not isinstance(platforms, dict):
        return []
    active = platforms.get("active")
    if not isinstance(active, list) or not active:
        return ["platforms.active deve ser lista não-vazia (RULE-004)"]
    invalid = [p for p in active if p not in _VALID_PLATFORMS]
    if invalid:
        return [f"platforms.active contém valores inválidos: {invalid} (RULE-004)"]
    return []


def _check_feature_roots(project_root: Path, data: dict[str, Any]) -> list[str]:
    """RULE-008: paths.feature-roots devem existir no disco (soft check)."""
    out: list[str] = []
    paths = data.get("paths") if isinstance(data, dict) else None
    if not isinstance(paths, dict):
        return out
    roots = paths.get("feature-roots") or {}
    if not isinstance(roots, dict):
        return out
    for plat, raw_path in roots.items():
        if not isinstance(raw_path, str):
            continue
        # Ignora globs (**) — head do path basta pra checar existência.
        head = raw_path.split("**", 1)[0].rstrip("/")
        if head and not (project_root / head).exists():
            out.append(f"paths.feature-roots.{plat} aponta pra {raw_path} (head '{head}' não existe)")
    return out


def _check_backend(project_root: Path, data: dict[str, Any]) -> list[str]:
    """RULE-019..024: backend multi-axis cell structure enforcement.

    Substitui RULE-010/011 (legacy `backend.provider` enum) removidos em
    DET-6 Phase B. Shape canônico vive em ``docs/schemas/backend-axes.md``.

    Regras enforçadas:
      · RULE-019  ``backend.<axis>`` em enum canônico (8 axes)
      · RULE-020  ``backend.<axis>.<platform>`` ∈ platforms.active OR `null`
      · RULE-021  cell.card (quando cell != null) referencia card em cards/
      · RULE-022  cell.status ∈ {active, migrating-to, deprecated}
      · RULE-023  cell.migrating-to REQUIRED quando status=migrating-to;
                  MUST be absent caso contrário
      · RULE-024  cell.migrating-to (quando presente) referencia card em cards/

    Cell shape canônica:
        backend:
          <axis>:                  # ∈ _VALID_BACKEND_AXES
            <platform>:            # ∈ platforms.active OR "all-platforms" OR null
              card: <card-id>
              status: active | migrating-to | deprecated
              migrating-to: <card-id>  # required iff status=migrating-to
    """
    out: list[str] = []
    backend = data.get("backend") if isinstance(data, dict) else None
    if not isinstance(backend, dict):
        return ["backend block ausente ou não-objeto (RULE-019)"]

    platforms_block = data.get("platforms") if isinstance(data, dict) else None
    platforms_active: set[str] = set()
    if isinstance(platforms_block, dict):
        raw_active = platforms_block.get("active") or []
        if isinstance(raw_active, list):
            platforms_active = {p for p in raw_active if isinstance(p, str) and p}

    cards_root = cards_dir(project_root)

    for axis, axis_block in backend.items():
        # RULE-019 — axis enum.
        if axis not in _VALID_BACKEND_AXES:
            out.append(
                f"backend.{axis} não está em {sorted(_VALID_BACKEND_AXES)} (RULE-019)"
            )
            continue
        if axis_block is None:
            continue  # axis explicitamente vazio é OK
        if not isinstance(axis_block, dict):
            out.append(
                f"backend.{axis} deve ser dict (ou null), got {type(axis_block).__name__} (RULE-019)"
            )
            continue

        for platform_key, cell in axis_block.items():
            # RULE-020 — platform ∈ platforms.active OR "all-platforms".
            if (
                platform_key != "all-platforms"
                and platform_key not in platforms_active
            ):
                out.append(
                    f"backend.{axis}.{platform_key}: platform desconhecida "
                    f"(não está em platforms.active={sorted(platforms_active)} "
                    f"e não é 'all-platforms') (RULE-020)"
                )
                # ainda valida o resto da cell pra surface mais erros num só pass.

            if cell is None:
                continue  # cell vazia OK
            if not isinstance(cell, dict):
                out.append(
                    f"backend.{axis}.{platform_key} deve ser dict ou null, "
                    f"got {type(cell).__name__} (RULE-019)"
                )
                continue

            # RULE-021 — cell.card existe em cards/ (canonical OR local overlay).
            # Espelha `engine/reconfigure._card_exists`: snapshot canonical
            # primeiro, depois `.claude/cards/local/<name>/card.yaml`. Local
            # cards são fonte legítima (orphan workflow Step 7.5 + Gap 5).
            card_id = cell.get("card")
            if not isinstance(card_id, str) or not card_id:
                out.append(
                    f"backend.{axis}.{platform_key}.card obrigatório (string não-vazia) (RULE-021)"
                )
            else:
                canonical_yaml = cards_root / card_id / "card.yaml"
                local_yaml = (
                    project_root / ".claude" / "cards" / "local" / card_id / "card.yaml"
                )
                if not canonical_yaml.is_file() and not local_yaml.is_file():
                    out.append(
                        f"backend.{axis}.{platform_key}.card={card_id!r} não existe "
                        f"em {cards_root}/<name>/card.yaml nem em "
                        f".claude/cards/local/<name>/card.yaml (RULE-021)"
                    )

            # RULE-022 — status enum.
            status = cell.get("status")
            if status is None:
                out.append(
                    f"backend.{axis}.{platform_key}.status obrigatório "
                    f"(esperado um de {sorted(_VALID_CELL_STATUSES)}) (RULE-022)"
                )
            elif status not in _VALID_CELL_STATUSES:
                out.append(
                    f"backend.{axis}.{platform_key}.status={status!r} inválido — "
                    f"esperado um de {sorted(_VALID_CELL_STATUSES)} (RULE-022)"
                )

            # RULE-023 — migrating-to consistency.
            migrating_to = cell.get("migrating-to")
            if status == "migrating-to":
                if not isinstance(migrating_to, str) or not migrating_to:
                    out.append(
                        f"backend.{axis}.{platform_key}: status=migrating-to "
                        f"requer migrating-to (string não-vazia) (RULE-023)"
                    )
            elif migrating_to is not None:
                out.append(
                    f"backend.{axis}.{platform_key}: migrating-to presente "
                    f"mas status={status!r} (esperado status=migrating-to) (RULE-023)"
                )

            # RULE-024 — migrating-to referencia card existente (canonical OR local).
            if isinstance(migrating_to, str) and migrating_to:
                canonical_mig = cards_root / migrating_to / "card.yaml"
                local_mig = (
                    project_root / ".claude" / "cards" / "local" / migrating_to / "card.yaml"
                )
                if not canonical_mig.is_file() and not local_mig.is_file():
                    out.append(
                        f"backend.{axis}.{platform_key}.migrating-to={migrating_to!r} "
                        f"não existe em {cards_root}/<name>/card.yaml nem em "
                        f".claude/cards/local/<name>/card.yaml (RULE-024)"
                    )
    return out


def _check_readiness_strictness(data: dict[str, Any]) -> list[str]:
    """RULE-013: workflow.readiness-strictness ∈ {strict, standard, lean}."""
    workflow = data.get("workflow") if isinstance(data, dict) else None
    if not isinstance(workflow, dict):
        return []
    strictness = workflow.get("readiness-strictness")
    if strictness is not None and strictness not in _VALID_STRICTNESS:
        return [
            f"workflow.readiness-strictness {strictness!r} inválido — esperado um de {sorted(_VALID_STRICTNESS)} (RULE-013)"
        ]
    return []


def _check_l1_mutation_lock(project_root: Path) -> list[str]:
    """RULE-018: nenhuma feature L1 pode estar em phase ativa.

    Lê `.claude/memory/L1/*/status.json` e procura `state` ∈ {planning,
    implementing, verifying}. Se houver, mutação de cards (este validator é
    chamado antes de reconfigure ops mutantes) deve bloquear.
    """
    import json

    out: list[str] = []
    l1_root = memory_dir(project_root) / "L1"
    if not l1_root.is_dir():
        return out
    for slug_dir in l1_root.iterdir():
        if not slug_dir.is_dir():
            continue
        status_path = slug_dir / "status.json"
        if not status_path.is_file():
            continue
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        state = data.get("state") if isinstance(data, dict) else None
        if state in _L1_ACTIVE_STATES:
            out.append(f"L1/{slug_dir.name} em state={state!r} (RULE-018: card mutation bloqueada)")
    return out


def _check_card_sha(project_root: Path, data: dict[str, Any]) -> list[str]:
    """Compare each active card's recorded sha256 vs disk."""
    out: list[str] = []
    cards_root = cards_dir(project_root)
    for card in (data.get("cards") or {}).get("active") or []:
        if not isinstance(card, dict):
            continue
        name = card.get("name")
        recorded = card.get("sha256")
        if not name or not isinstance(recorded, str):
            continue
        if "..." in recorded or len(recorded) < 16:
            continue  # placeholder in template/example
        card_yaml = cards_root / name / "card.yaml"
        if not card_yaml.is_file():
            out.append(f"card {name}: snapshot ausente em {card_yaml}")
            continue
        try:
            actual = file_sha256(card_yaml)
        except Exception as exc:  # noqa: BLE001
            out.append(f"card {name}: sha256 erro ({exc})")
            continue
        if actual != recorded:
            out.append(f"card {name}: sha256 mismatch (recorded {recorded[:8]}… vs disk {actual[:8]}…)")
    return out


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate workflow-config.yaml schema + card snapshot integrity."""
    cfg_path = workflow_config_path(project_root)
    if not cfg_path.is_file():
        return result_fail(
            "workflow-config.yaml ausente",
            what_failed=f"missing {cfg_path}",
            where=str(cfg_path),
            why=["Sem workflow-config, nenhum command funciona."],
            paths=make_paths(
                "Rodar `forge init` pra criar o arquivo",
                "init detecta o projeto e escreve o config.",
                "Restaurar do git — `git checkout -- .claude/workflow-config.yaml`",
                "Se foi removido por engano.",
                "Pedir backup ao time — `git log -- .claude/workflow-config.yaml`",
                "Se nunca foi committed, alguém local pode ter cópia.",
            ),
        )

    try:
        data = read_yaml_or_default(cfg_path, {}) or {}
    except Exception as exc:  # noqa: BLE001
        return result_fail(
            "workflow-config.yaml YAML parse error",
            what_failed=str(exc),
            where=str(cfg_path),
            why=["forge não consegue parsear o config — todos os comandos falham."],
            paths=make_paths(
                "Corrigir o YAML manualmente",
                "Indentação ou aspas geralmente.",
                "Reverter pro último .bak — `cp workflow-config.yaml.bak workflow-config.yaml`",
                "Atomic-write deixa .bak quando configurado.",
                "Re-rodar `forge reconfigure` em outra branch",
                "Para regenerar do zero preservando dados.",
            ),
        )

    if data.get("schema-version") != 1:
        return result_fail(
            f"schema-version inválido: {data.get('schema-version')!r}",
            what_failed=f"got {data.get('schema-version')!r}, expected 1",
            where=str(cfg_path),
            why=["v1 é a única versão suportada (RULE-001)"],
            paths=make_paths(
                "Setar schema-version: 1 no topo",
                "v2 ainda não existe.",
                "Rodar migrador — `forge raw migrator-N-to-1`",
                "Se o config veio de uma versão futura.",
                "Re-init — `forge init` em backup",
                "Se quiser começar do zero.",
            ),
        )

    missing = _check_required(data)
    if missing:
        return result_fail(
            f"{len(missing)} bloco(s) top-level obrigatório(s) faltando",
            what_failed=", ".join(missing),
            where=str(cfg_path),
            why=["Cada bloco é referenciado por sub-agents — ausência quebra dispatch"],
            paths=make_paths(
                "Re-rodar `forge reconfigure` pra repopular os blocos faltantes",
                "Re-extração mantém o resto intacto.",
                "Restaurar do git — checkout do último config bom",
                "Se a edição manual deixou inconsistente.",
                "Re-init em sandbox — `forge init` em branch nova",
                "Pra comparar contra um config recém-gerado.",
            ),
        )

    # ── Regras estruturais adicionais (RULE-002, 004, 013 + 019..024) ───────
    schema_violations: list[str] = []
    schema_violations.extend(_check_project_slug(data))
    schema_violations.extend(_check_platforms_active(data))
    schema_violations.extend(_check_backend(project_root, data))
    schema_violations.extend(_check_readiness_strictness(data))

    if schema_violations:
        return result_fail(
            f"{len(schema_violations)} violação(ões) estrutural(is)",
            what_failed="; ".join(schema_violations[:3])
            + (f" (+{len(schema_violations) - 3} more)" if len(schema_violations) > 3 else ""),
            where=str(cfg_path),
            why=[
                "RULE-002/004/013/019..024 garantem que sub-agents leem campos com formato esperado.",
                "Cell sem card existente = handlers downstream quebram silenciosamente.",
            ],
            paths=make_paths(
                "Corrigir o YAML manualmente seguindo as RULEs apontadas",
                "Cada violation cita o código da RULE em docs/schemas/{workflow-config,backend-axes}.md.",
                "Re-rodar `forge reconfigure` se o erro for em bloco inteiro",
                "Reconfigure regenera os blocos preservando customizações.",
                "Restaurar do git — `git checkout -- .claude/workflow-config.yaml`",
                "Se a edição manual deixou inconsistente.",
            ),
        )

    # ── RULE-018: mutation lock — informativo (validator não muta) ──────────
    locks = _check_l1_mutation_lock(project_root)

    # ── RULE-008: feature-roots no disco (soft warn) ────────────────────────
    soft_warns: list[str] = _check_feature_roots(project_root, data)

    sha_mismatches = _check_card_sha(project_root, data)
    if sha_mismatches:
        return result_fail(
            f"{len(sha_mismatches)} card(s) com sha256 fora de sincronia",
            what_failed="; ".join(sha_mismatches[:3]),
            where=str(cards_dir(project_root)),
            why=[
                "RULE-006: every card's recorded sha256 must match disk.",
                "Snapshot drift = comportamento divergente entre projetos.",
            ],
            paths=make_paths(
                "Re-sincronizar — `forge reconfigure → atualizar card do canonical`",
                "Atualiza sha256 + agent-contributions juntos.",
                "Reverter o card no disco — `git checkout cards/{name}/`",
                "Se a edição local foi acidental.",
                "Remover o card — `forge reconfigure → remover card`",
                "Se o card não é mais necessário.",
            ),
        )

    # Soft warns combinados (feature-roots ausentes + L1 lock informativo)
    combined_warns: list[str] = []
    combined_warns.extend(soft_warns)
    if locks:
        combined_warns.extend(
            f"{l} — operações mutantes via forge reconfigure bloqueadas"
            for l in locks
        )

    if combined_warns:
        return result_warn(
            f"workflow-config OK com {len(combined_warns)} warning(s)",
            what_failed="; ".join(combined_warns[:3])
            + (f" (+{len(combined_warns) - 3} more)" if len(combined_warns) > 3 else ""),
            where=str(cfg_path),
            why=[
                "RULE-008: paths.feature-roots ausentes não bloqueiam mas degradam discovery.",
                "RULE-018: L1 em phase ativa bloqueia mutação de cards.",
            ],
        )

    return result_pass(
        f"workflow-config OK ({len(data.get('cards', {}).get('active') or [])} cards ativos)"
    )


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
