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
        QAExtensionsCollisionError: colisão de `name` entre cards
            (subclass de QAExtensionsValidationError; Regra 1).

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
        contributes = aud.get("contributes", {})
        if not isinstance(contributes, dict):
            raise QAExtensionsValidationError(
                f"{card_path}: auditor {name!r} contributes deve ser mapping, "
                f"got {type(contributes).__name__}"
            )
        agents = contributes.get("agents", [])
        if not isinstance(agents, list):
            raise QAExtensionsValidationError(
                f"{card_path}: auditor {name!r} contributes.agents deve ser lista, "
                f"got {type(agents).__name__}"
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

        # Regra 1 — colisão cross-card (sempre, mesmo se disabled — shape).
        # Disabled é runtime toggle; colisão estrutural é load-bearing
        # pra integridade do pool de auditores.
        if other_cards:
            for other_path, other_data in other_cards.items():
                if other_path == str(card_path):
                    continue
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
