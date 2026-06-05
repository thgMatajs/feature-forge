"""Validator: qa-report.json schema (v1) — gerado por forge qa Phase 4.

Schema fonte: docs/schemas/qa-report.md.
"""

from __future__ import annotations

from typing import Any


class QAReportValidationError(ValueError):
    """qa-report.json não cumpre o schema v1."""


_VALID_VERDICTS = {"BLOCK", "FLAG", "PASS"}
_VALID_SCOPE_TYPES = {"feature", "screen", "task", "paranoid"}
_REQUIRED_SEVERITY_KEYS = {"critical", "high", "medium", "low", "info"}
_REQUIRED_VECTOR_KEYS = {"spec-vs-spec", "coverage", "chaos", "validator-claim"}


def validate_qa_report(data: dict[str, Any]) -> None:
    """Valida o dict carregado do qa-report.json. Raise em qualquer desvio.

    Política mentor-calma: mensagem de erro nomeia o campo + o que esperava.
    """
    if not isinstance(data, dict):
        raise QAReportValidationError("qa-report deve ser dict no topo")

    sv = data.get("schema_version")
    if sv != 1:
        raise QAReportValidationError(
            f"schema_version esperado=1, recebido={sv!r}. "
            f"Bump exige mudança breaking documentada."
        )

    for required in ("run", "verdict", "summary", "findings"):
        if required not in data:
            raise QAReportValidationError(f"campo obrigatório ausente: {required!r}")

    verdict = data["verdict"]
    if verdict not in _VALID_VERDICTS:
        raise QAReportValidationError(
            f"verdict={verdict!r} inválido. Valores aceitos: {sorted(_VALID_VERDICTS)}"
        )

    findings = data["findings"]
    if not isinstance(findings, list):
        raise QAReportValidationError(
            f"findings deve ser list, recebido tipo {type(findings).__name__}"
        )

    run = data["run"]
    if not isinstance(run, dict):
        raise QAReportValidationError("run deve ser dict")
    for required in ("id", "scope", "started_at", "finished_at", "duration_s"):
        if required not in run:
            raise QAReportValidationError(f"run.{required} ausente")

    scope = run["scope"]
    if not isinstance(scope, dict):
        raise QAReportValidationError(
            f"run.scope deve ser dict, recebido tipo {type(scope).__name__}"
        )
    if scope.get("type") not in _VALID_SCOPE_TYPES:
        raise QAReportValidationError(
            f"run.scope.type={scope.get('type')!r} inválido. "
            f"Aceitos: {sorted(_VALID_SCOPE_TYPES)}"
        )

    summary = data["summary"]
    by_sev = summary.get("by_severity", {})
    if set(by_sev.keys()) != _REQUIRED_SEVERITY_KEYS:
        raise QAReportValidationError(
            f"summary.by_severity precisa de keys {sorted(_REQUIRED_SEVERITY_KEYS)}; "
            f"recebido: {sorted(by_sev.keys())}"
        )

    by_vec = summary.get("by_vector", {})
    if not _REQUIRED_VECTOR_KEYS.issubset(by_vec.keys()):
        raise QAReportValidationError(
            f"summary.by_vector precisa pelo menos {sorted(_REQUIRED_VECTOR_KEYS)}; "
            f"recebido: {sorted(by_vec.keys())}"
        )

    total = summary.get("total_findings", 0)
    sev_sum = sum(by_sev.values())
    if sev_sum != total:
        raise QAReportValidationError(
            f"summary.total_findings={total} não bate com sum(by_severity)={sev_sum}"
        )

    # Schema doc §6.1 linha 75: summary.total_findings == len(findings).
    # Defesa contra synthesis-phase bugs onde contadores divergem do array real.
    if len(findings) != total:
        raise QAReportValidationError(
            f"summary.total_findings={total} não bate com len(findings)={len(findings)}"
        )
