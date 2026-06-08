"""Validator: campo `qa-extensions:` em card.yaml — overlay-aware (Gap 5).

Schema fonte: docs/schemas/qa-extensions.md (5 regras enumeradas).
Política de colisão: canon×local → hard fail (Decisão 28 / Gap 5 Approach A).

Interface: library raise-based, consumido por `engine/cards/loader.py` no
startup (Task 7.1) e por `validate_card_yaml.py` na cascade default.
Validators de cascade (forge verify) usam `result_fail`/`result_pass` via
`_common.py` — esta interface raise-based é o pareamento canônico pra
loaders e callers que querem propagar exception nativa.

Política mentor-calma: mensagens nomeiam o campo + valor recebido + path
do card. Em colisão, nomeia ambos os cards envolvidos pra que o operador
veja imediatamente quem está em conflito.

Reuso (mandamento #3): `_common.load_catalog` é a fonte única de catálogo
efetivo (canon ∪ local overlay). NÃO duplicar a lógica aqui.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from validators._common import load_catalog


class QAExtensionsValidationError(ValueError):
    """qa-extensions: bloco inválido em card.yaml."""


class QAExtensionsCollisionError(QAExtensionsValidationError):
    """Mesmo auditor `name` declarado em canon AND local — hard fail (Decisão 28).

    Approach A: sem merge silencioso, sem prompt de override. Operador
    renomeia ou remove o auditor duplicado manualmente.
    """


_VALID_PHASES = {"static", "generative"}


def validate_qa_extensions(
    card_path: Path,
    card_data: dict[str, Any],
    *,
    other_cards: dict[str, dict[str, Any]] | None = None,
    project_root: Path | None = None,
    extensions_disabled: set[str] | None = None,
) -> None:
    """Valida o campo `qa-extensions:` de um card.

    Args:
        card_path: Path absoluto do card.yaml sendo validado. Usado pra
            resolver paths relativos em `contributes.agents[]` e pra
            compor a mensagem de erro (ambos lados em colisão).
        card_data: dict top-level do card já parseado.
        other_cards: mapping `{str(card_path): card_data}` dos outros cards
            já carregados — pra detectar colisão cross-card de `name`.
            Caller (loader) injeta o universo conhecido. `None` ou `{}`
            pula Regra 1.
        project_root: raiz do projeto consumidor; usado pra resolver o
            catálogo efetivo via `_common.load_catalog` (overlay-aware).
            `None` pula Regra 4 (capability check).
        extensions_disabled: set de auditor names desabilitados em
            `workflow-config.yaml` (`qa.extensions.disabled`). Auditor
            cujo nome está aqui passa Regra 4 (capability), mas continua
            sujeito a Regras 1-3 estruturais. Regra 5 (semântica).

    Raises:
        QAExtensionsValidationError: shape inválido (Regras 2, 3, 4 +
            defensive type guards).
        QAExtensionsCollisionError: colisão de `name` entre cards OU
            intra-card (subclass de QAExtensionsValidationError; Regra 1).
        CatalogOverlayError: propagado de `_common.load_catalog` quando
            o overlay local está malformado (não capturado aqui — overlay
            é pré-condição da cascade; caller que precisa diferenciar
            deve catchar `CatalogOverlayError` antes de
            `QAExtensionsValidationError`).

    Returns:
        None em sucesso (campo opcional → ausência também passa).
    """
    qa_ext = card_data.get("qa-extensions")
    if qa_ext is None:
        return  # campo opcional

    if not isinstance(qa_ext, dict):
        raise QAExtensionsValidationError(
            f"{card_path}: qa-extensions deve ser dict, got {type(qa_ext).__name__}"
        )

    auditors = qa_ext.get("auditors", [])
    if not isinstance(auditors, list):
        raise QAExtensionsValidationError(
            f"{card_path}: qa-extensions.auditors deve ser lista, "
            f"got {type(auditors).__name__}"
        )

    # QA-11 Wave 2: env-needs (opcional, lista de strings non-empty sem whitespace).
    # Spec §3: validator só checa SHAPE, não SEMÂNTICA. Pattern sensitive
    # (GITHUB_TOKEN, AWS_*, etc.) NÃO é rejeitado aqui — decisão de
    # rejeição/grant fica pra runtime (init/reconfigure, Wave 3).
    env_needs = qa_ext.get("env-needs")
    if env_needs is not None:
        if not isinstance(env_needs, list):
            raise QAExtensionsValidationError(
                f"{card_path}: qa-extensions.env-needs deve ser lista "
                f"(recebido {type(env_needs).__name__})"
            )
        for idx, item in enumerate(env_needs):
            if not isinstance(item, str):
                raise QAExtensionsValidationError(
                    f"{card_path}: qa-extensions.env-needs[{idx}] deve ser string "
                    f"(recebido {type(item).__name__}: {item!r})"
                )
            if not item or item != item.strip() or any(c.isspace() for c in item):
                raise QAExtensionsValidationError(
                    f"{card_path}: qa-extensions.env-needs[{idx}] inválido "
                    f"({item!r}): deve ser non-empty sem whitespace interno"
                )

    disabled = extensions_disabled or set()

    # Catálogo efetivo (canon ∪ local). Só carrega quando há requires a
    # checar — load_catalog faz I/O leve (read YAML local), mas
    # consistência manda lazy-load.
    catalog_active: frozenset[str] | None = None

    def _get_active() -> frozenset[str]:
        nonlocal catalog_active
        if catalog_active is None:
            if project_root is None:
                catalog_active = frozenset()
            else:
                cat = load_catalog(project_root)
                catalog_active = cat.active
        return catalog_active

    # IN-02: normaliza chaves de other_cards pra str e filtra o próprio
    # card aqui, em vez de comparar `Path == str(card_path)` dentro do
    # loop (que retorna False silenciosamente quando caller esquece
    # `str()` na chave, causando self-collision spurious).
    normalized_others: dict[str, dict[str, Any]] = {}
    if other_cards:
        self_key = str(card_path)
        for other_path, other_data in other_cards.items():
            other_key = str(other_path)
            if other_key == self_key:
                continue
            normalized_others[other_key] = other_data

    # WR-01: tracking de nomes vistos DENTRO deste card pra detectar
    # colisão intra-card (mesmo `name` 2x na mesma `auditors[]`).
    # Spec §6.3: "name único cross canon ∪ local" — cross inclui o caso
    # trivial intra-card como subset.
    seen_names_local: set[str] = set()

    for idx, aud in enumerate(auditors):
        if not isinstance(aud, dict):
            raise QAExtensionsValidationError(
                f"{card_path}: auditor[{idx}] deve ser mapping, "
                f"got {type(aud).__name__}"
            )

        name = aud.get("name")
        if not name or not isinstance(name, str):
            raise QAExtensionsValidationError(
                f"{card_path}: auditor[{idx}] sem campo `name` (str não-vazia)"
            )

        # Regra 2 — phase enum strict (sempre, mesmo se disabled — shape).
        phase = aud.get("phase")
        if phase not in _VALID_PHASES:
            raise QAExtensionsValidationError(
                f"{card_path}: auditor {name!r} phase={phase!r} inválida; "
                f"aceitos: {sorted(_VALID_PHASES)} "
                f"(Phase 0/3/4/5 são core-only, não podem ser estendidas)"
            )

        # Regra 3 — agents existem (sempre, mesmo se disabled).
        # WR-02: `contributes` + `contributes.agents` são REQUIRED por
        # schema (docs/schemas/qa-extensions.md §86). Validar explícita-
        # mente, não defaultar pra `{}`/`[]` — auditor sem prompt é
        # auditor inutilizável. Reincidência da lição Task 2.2 HI-01..03.
        if "contributes" not in aud:
            raise QAExtensionsValidationError(
                f"{card_path}: auditor {name!r} sem campo `contributes` "
                f"(required: contributes.agents[])"
            )
        contributes = aud["contributes"]
        if not isinstance(contributes, dict):
            raise QAExtensionsValidationError(
                f"{card_path}: auditor {name!r} contributes deve ser mapping, "
                f"got {type(contributes).__name__}"
            )
        if "agents" not in contributes:
            raise QAExtensionsValidationError(
                f"{card_path}: auditor {name!r} sem campo `contributes.agents` "
                f"(required: lista de paths .md relativos ao card)"
            )
        agents = contributes["agents"]
        if not isinstance(agents, list):
            raise QAExtensionsValidationError(
                f"{card_path}: auditor {name!r} contributes.agents deve ser lista, "
                f"got {type(agents).__name__}"
            )
        if not agents:
            raise QAExtensionsValidationError(
                f"{card_path}: auditor {name!r} contributes.agents lista vazia — "
                f"auditor sem prompt é inutilizável"
            )
        for agent_rel in agents:
            if not isinstance(agent_rel, str) or not agent_rel:
                raise QAExtensionsValidationError(
                    f"{card_path}: auditor {name!r} contributes.agents tem "
                    f"entrada não-string ou vazia"
                )
            agent_path = card_path.parent / agent_rel
            if not agent_path.exists():
                raise QAExtensionsValidationError(
                    f"{card_path}: auditor {name!r} referencia agent inexistente: "
                    f"{agent_path} (convenção: <card-dir>/agent-contributions/<file>.md)"
                )

        # Regra 4 — requires capabilities no catálogo (skip se disabled).
        requires = aud.get("requires", [])
        if not isinstance(requires, list):
            raise QAExtensionsValidationError(
                f"{card_path}: auditor {name!r} requires deve ser lista, "
                f"got {type(requires).__name__}"
            )
        if name not in disabled:
            for req in requires:
                if not isinstance(req, str) or not req:
                    raise QAExtensionsValidationError(
                        f"{card_path}: auditor {name!r} requires tem entrada "
                        f"não-string ou vazia"
                    )
                if req not in _get_active():
                    raise QAExtensionsValidationError(
                        f"{card_path}: auditor {name!r} requires capability "
                        f"{req!r} não declarada no catálogo (canon ∪ local). "
                        f"Adicione ao docs/schemas/capability-labels.md (canon) "
                        f"ou .claude/inventory/capability-labels.local.yaml (overlay)."
                    )

        # Regra 1 (parte a) — colisão intra-card (mesmo `name` 2x na
        # mesma `auditors[]`). Spec §6.3 "name único cross canon ∪ local"
        # cobre cross-card; intra-card é subset trivial. Fechar este
        # buraco aqui evita pressão futura no loader (Task 7.1).
        if name in seen_names_local:
            raise QAExtensionsCollisionError(
                f"qa-extensions name collision intra-card: auditor name "
                f"{name!r} duplicado dentro do mesmo card {card_path}. "
                f"Approach A (Decisão 28): hard fail sem merge silencioso. "
                f"Renomeie ou remova o auditor duplicado."
            )
        seen_names_local.add(name)

        # Regra 1 (parte b) — colisão cross-card (sempre, mesmo se
        # disabled — shape). Disabled é runtime toggle; colisão
        # estrutural é load-bearing pra integridade do pool de auditores.
        if normalized_others:
            for other_path, other_data in normalized_others.items():
                other_ext = other_data.get("qa-extensions") or {}
                if not isinstance(other_ext, dict):
                    continue
                other_auditors = other_ext.get("auditors") or []
                if not isinstance(other_auditors, list):
                    continue
                other_names = {
                    a.get("name")
                    for a in other_auditors
                    if isinstance(a, dict) and isinstance(a.get("name"), str)
                }
                if name in other_names:
                    raise QAExtensionsCollisionError(
                        f"qa-extensions name collision: {name!r} declarado em "
                        f"dois cards:\n"
                        f"  · {card_path}\n"
                        f"  · {other_path}\n"
                        f"Approach A (Decisão 28): hard fail sem merge silencioso. "
                        f"Renomeie ou remova o auditor duplicado em um dos cards."
                    )
