"""Validator: shape individual de um qa-finding.

Schema fonte: docs/schemas/qa-finding.md.

Interface: library raise-based (não CLI cascade). Consumido por auditores
(Phase 2/3) ao emitir drafts e pelo synthesizer (Phase 4) ao consolidar
em qa-report.json. Validators de cascade (forge verify) usam pattern
result_fail/result_pass via _common.py — não aplicável aqui.

Política mentor-calma: cada mensagem nomeia o campo e o valor recebido.
"""

from __future__ import annotations

import re
from typing import Any


class QAFindingValidationError(ValueError):
    """qa-finding individual não cumpre o schema v1."""


_VALID_SEVERITY = {"critical", "high", "medium", "low", "info"}
_CORE_VECTORS = {"spec-vs-spec", "coverage", "chaos", "validator-claim"}
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_TOP = {
    "id",
    "fingerprint",
    "vector",
    "severity",
    "title",
    "description",
    "scope",
    "evidence",
    "proposed_evolution",
    "created_at",
}


def validate_qa_finding(
    data: dict[str, Any],
    known_extension_vectors: set[str] | None = None,
) -> None:
    """Valida shape individual de um finding. Raise em qualquer desvio.

    Args:
        data: dict carregado do finding draft (ou item de findings[] no report).
        known_extension_vectors: nomes de auditores custom registrados via
            qa-extensions cards. Quando fornecido, vector names listados aqui
            são aceitos além do core enum. Default vazio (apenas core).

    Raises:
        QAFindingValidationError: se shape, tipos, enums ou regex divergem.
    """
    if not isinstance(data, dict):
        raise QAFindingValidationError(
            f"finding deve ser dict no topo, recebido tipo {type(data).__name__}"
        )

    missing = _REQUIRED_TOP - set(data.keys())
    if missing:
        raise QAFindingValidationError(
            f"finding com campos obrigatórios ausentes: {sorted(missing)}"
        )

    fingerprint = data["fingerprint"]
    if not isinstance(fingerprint, str) or not _FINGERPRINT_RE.match(fingerprint):
        raise QAFindingValidationError(
            f"fingerprint inválido (esperado sha256 hex lowercase 64-char): "
            f"{fingerprint!r}"
        )

    severity = data["severity"]
    if severity not in _VALID_SEVERITY:
        raise QAFindingValidationError(
            f"severity={severity!r} inválida; aceitos: {sorted(_VALID_SEVERITY)}"
        )

    vector = data["vector"]
    valid_vectors = _CORE_VECTORS | (known_extension_vectors or set())
    if vector not in valid_vectors:
        raise QAFindingValidationError(
            f"vector={vector!r} inválido. Core: {sorted(_CORE_VECTORS)}. "
            f"Extension registrados: {sorted(known_extension_vectors or [])}"
        )

    evidence = data["evidence"]
    if not isinstance(evidence, dict):
        raise QAFindingValidationError(
            f"evidence deve ser dict, recebido tipo {type(evidence).__name__}"
        )

    if vector == "validator-claim" and "sandbox_result" not in evidence:
        raise QAFindingValidationError(
            "vector=validator-claim exige evidence.sandbox_result "
            "(subprocess executado no sandbox)"
        )

    pe = data["proposed_evolution"]
    if not isinstance(pe, dict):
        raise QAFindingValidationError(
            f"proposed_evolution deve ser dict, recebido tipo {type(pe).__name__}"
        )
    if "type" not in pe:
        raise QAFindingValidationError("proposed_evolution.type ausente")
    pe_type = pe["type"]
    if not isinstance(pe_type, str) or not pe_type.startswith("qa-finding-"):
        raise QAFindingValidationError(
            f"proposed_evolution.type deve começar com 'qa-finding-'; "
            f"recebido {pe_type!r}"
        )
