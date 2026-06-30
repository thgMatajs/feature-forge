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
_CORE_VECTORS = {
    "spec-vs-spec",
    "impl-vs-spec",
    "coverage",
    "chaos",
    "validator-claim",
}
# A9 (review pr27 r2): vetores DERIVADOS pelo engine na Phase 3/4 — não vêm de
# um auditor LLM, mas de findings_from_sandbox_results (breach/timeout) e do
# caminho de validator irresolvível (A4/A7). Hoje o engine nunca chama
# validate_qa_finding nesses derivados (validate_qa_report só exige os 5 core
# como subset), então a omissão é inócua. Adicionamos pra future-proofing: se
# alguém wirear validate_qa_finding nos derivados, eles não serão rejeitados.
# Additive only — não remove nem altera o enum core.
_ENGINE_VECTORS = {
    "sandbox-breach",
    "sandbox-timeout",
    "validator-claim-unresolvable",
}
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")
_ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
# Case-insensitive: IDs gerados a partir de run_id (ISO 8601) carregam
# `T` e `Z` uppercase no meio, ex.: `qa-2026-06-08T12-30-45Z-0001`.
_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*-\d{4}$")
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

    finding_id = data["id"]
    if not isinstance(finding_id, str) or not _ID_RE.fullmatch(finding_id):
        raise QAFindingValidationError(
            f"id inválido (esperado '<slug>-NNNN', case-insensitive — IDs "
            f"derivados de run_id ISO 8601 carregam T/Z uppercase. Ex.: "
            f"'qa-<run-id>-0007' ou '<auditor>-0001'): {finding_id!r}"
        )

    fingerprint = data["fingerprint"]
    if not isinstance(fingerprint, str) or not _FINGERPRINT_RE.fullmatch(fingerprint):
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
    valid_vectors = (
        _CORE_VECTORS | _ENGINE_VECTORS | (known_extension_vectors or set())
    )
    if vector not in valid_vectors:
        msg = (
            f"vector={vector!r} inválido. Core: {sorted(_CORE_VECTORS)}. "
            f"Engine-derived: {sorted(_ENGINE_VECTORS)}."
        )
        if known_extension_vectors:
            msg += f" Extensions registrados: {sorted(known_extension_vectors)}."
        raise QAFindingValidationError(msg)

    scope = data["scope"]
    if not isinstance(scope, dict):
        raise QAFindingValidationError(
            f"scope deve ser dict, recebido tipo {type(scope).__name__}"
        )
    if "files" not in scope:
        raise QAFindingValidationError("scope.files ausente (required)")
    files = scope["files"]
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        raise QAFindingValidationError(
            "scope.files deve ser list[str], "
            f"recebido tipo {type(files).__name__}"
        )
    if "feature" in scope and not isinstance(scope["feature"], str):
        raise QAFindingValidationError(
            f"scope.feature deve ser str, recebido tipo "
            f"{type(scope['feature']).__name__}"
        )

    evidence = data["evidence"]
    if not isinstance(evidence, dict):
        raise QAFindingValidationError(
            f"evidence deve ser dict, recebido tipo {type(evidence).__name__}"
        )

    for evidence_required in ("auditor", "auditor_reasoning"):
        if evidence_required not in evidence:
            raise QAFindingValidationError(
                f"evidence.{evidence_required} ausente (required pra todo vector)"
            )
        if not isinstance(evidence[evidence_required], str):
            raise QAFindingValidationError(
                f"evidence.{evidence_required} deve ser str, recebido tipo "
                f"{type(evidence[evidence_required]).__name__}"
            )

    if vector == "validator-claim":
        if "sandbox_result" not in evidence:
            raise QAFindingValidationError(
                "vector=validator-claim exige evidence.sandbox_result "
                "(subprocess executado no sandbox)"
            )
        sr = evidence["sandbox_result"]
        # Drafts (templates/qa-finding.template.json) carregam
        # sandbox_result=null antes da Phase 3 executar — auditor preenche
        # depois. Aceitamos None como placeholder explícito e pulamos a
        # validação interna; o conductor é responsável por trocar pelo
        # dict real antes do Phase 4 synthesis.
        if sr is not None:
            if not isinstance(sr, dict):
                raise QAFindingValidationError(
                    f"evidence.sandbox_result deve ser dict (ou null em drafts), "
                    f"recebido tipo {type(sr).__name__}"
                )
            for sr_required, expected_type, type_name in (
                ("exit_code", int, "int"),
                ("stdout", str, "str"),
                ("stderr", str, "str"),
                ("duration_s", (int, float), "number"),
            ):
                if sr_required not in sr:
                    raise QAFindingValidationError(
                        f"evidence.sandbox_result.{sr_required} ausente (required)"
                    )
                if not isinstance(sr[sr_required], expected_type):
                    raise QAFindingValidationError(
                        f"evidence.sandbox_result.{sr_required} deve ser {type_name}, "
                        f"recebido tipo {type(sr[sr_required]).__name__}"
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
    if "summary" not in pe:
        raise QAFindingValidationError("proposed_evolution.summary ausente")
    if not isinstance(pe["summary"], str):
        raise QAFindingValidationError(
            f"proposed_evolution.summary deve ser str, recebido tipo "
            f"{type(pe['summary']).__name__}"
        )
    if "actionable" not in pe:
        raise QAFindingValidationError("proposed_evolution.actionable ausente")
    if type(pe["actionable"]) is not bool:
        raise QAFindingValidationError(
            f"proposed_evolution.actionable deve ser bool, recebido tipo "
            f"{type(pe['actionable']).__name__}"
        )

    created_at = data["created_at"]
    if not isinstance(created_at, str) or not _ISO_UTC_RE.fullmatch(created_at):
        raise QAFindingValidationError(
            f"created_at deve ser ISO-8601 UTC com sufixo Z; recebido {created_at!r}"
        )
