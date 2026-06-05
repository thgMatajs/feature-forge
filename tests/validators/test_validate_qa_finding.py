"""Tests for validators/validate_qa_finding.py — schema-validates qa-finding shape.

Schema fonte: docs/schemas/qa-finding.md.
"""

from __future__ import annotations

import pytest

from validators.validate_qa_finding import (
    QAFindingValidationError,
    validate_qa_finding,
)


def _minimal_valid_finding() -> dict:
    """Finding completo válido per docs/schemas/qa-finding.md."""
    return {
        "id": "qa-2026-06-05T14-32-08Z-a1b2-0007",
        "fingerprint": "7a3f4d2c1b9e8a0f" * 4,  # 64-char hex lowercase
        "vector": "validator-claim",
        "severity": "critical",
        "title": "validate_data_contract.py passa fixture com email vazio",
        "description": (
            "Validator declara cobertura em docstring mas regex não rejeita string vazia. "
            "Fixture sintético com email='' passa sem erro (exit code 0)."
        ),
        "scope": {
            "feature": "lembrete-rega",
            "task": "TASK-0004",
            "files": [
                "tasks/TASK-0004.yaml",
                "validators/validate_data_contract.py",
            ],
        },
        "evidence": {
            "fixture_path": ".planning/qa/lembrete-rega/run/fixtures/empty-email.yaml",
            "sandbox_result": {
                "exit_code": 0,
                "stdout": "...",
                "stderr": "",
                "duration_s": 0.142,
            },
            "expected_exit_code": 1,
            "auditor": "validator-claim",
            "auditor_reasoning": "regex pattern não cobre string vazia.",
        },
        "proposed_evolution": {
            "type": "qa-finding-validator-claim",
            "target": "validators/validate_data_contract.py",
            "summary": "Estender regex pra rejeitar email vazio + adicionar test case",
            "actionable": True,
        },
        "created_at": "2026-06-05T14:33:51Z",
    }


def test_happy_path_validates():
    """Finding completo válido não levanta."""
    validate_qa_finding(_minimal_valid_finding())  # no raise


def test_top_level_must_be_dict():
    """Defensive: input não-dict (string) deve raise QAFindingValidationError, não AttributeError."""
    with pytest.raises(QAFindingValidationError, match="finding deve ser dict"):
        validate_qa_finding("not a dict")  # type: ignore[arg-type]


def test_missing_required_top_field_fails():
    """Ausência de campo obrigatório no topo deve raise nomeando o campo."""
    finding = _minimal_valid_finding()
    del finding["id"]
    with pytest.raises(QAFindingValidationError, match="obrigatórios ausentes"):
        validate_qa_finding(finding)


def test_fingerprint_invalid_format_fails():
    """Fingerprint não-hex ou wrong length deve raise (regex strict 64-char lowercase hex)."""
    finding = _minimal_valid_finding()
    finding["fingerprint"] = "not-a-real-hash"  # wrong length + non-hex
    with pytest.raises(QAFindingValidationError, match="fingerprint inválido"):
        validate_qa_finding(finding)


def test_fingerprint_uppercase_rejected():
    """Fingerprint deve ser lowercase — uppercase hex rejeitado pelo regex strict."""
    finding = _minimal_valid_finding()
    finding["fingerprint"] = "ABCDEF" + "0" * 58  # uppercase
    with pytest.raises(QAFindingValidationError, match="fingerprint inválido"):
        validate_qa_finding(finding)


def test_severity_enum_strict():
    """Severity fora do enum {critical, high, medium, low, info} deve raise."""
    finding = _minimal_valid_finding()
    finding["severity"] = "warn"
    with pytest.raises(QAFindingValidationError, match="severity"):
        validate_qa_finding(finding)


def test_vector_enum_strict_core():
    """Vector fora do core enum (sem extensions registrados) deve raise."""
    finding = _minimal_valid_finding()
    finding["vector"] = "random"
    with pytest.raises(QAFindingValidationError, match="vector"):
        validate_qa_finding(finding)


def test_vector_extension_accepted():
    """Vector registrado via known_extension_vectors deve passar."""
    finding = _minimal_valid_finding()
    finding["vector"] = "visual-fidelity"
    finding["evidence"] = {
        "auditor": "visual-fidelity",
        "auditor_reasoning": "card extension auditor",
    }
    finding["proposed_evolution"]["type"] = "qa-finding-visual-fidelity"
    validate_qa_finding(
        finding, known_extension_vectors={"visual-fidelity"}
    )  # no raise


def test_evidence_must_be_dict():
    """Defensive: evidence=string deve raise QAFindingValidationError, não AttributeError."""
    finding = _minimal_valid_finding()
    finding["evidence"] = "string instead of dict"
    with pytest.raises(QAFindingValidationError, match="evidence deve ser dict"):
        validate_qa_finding(finding)


def test_validator_claim_requires_sandbox_result():
    """vector=validator-claim sem evidence.sandbox_result deve raise (load-bearing pra evidence)."""
    finding = _minimal_valid_finding()
    # vector já é validator-claim no minimal
    del finding["evidence"]["sandbox_result"]
    with pytest.raises(QAFindingValidationError, match="sandbox_result"):
        validate_qa_finding(finding)


def test_proposed_evolution_must_be_dict():
    """Defensive: proposed_evolution=string deve raise QAFindingValidationError, não AttributeError."""
    finding = _minimal_valid_finding()
    finding["proposed_evolution"] = "string instead of dict"
    with pytest.raises(QAFindingValidationError, match="proposed_evolution"):
        validate_qa_finding(finding)


def test_proposed_evolution_type_missing():
    """proposed_evolution sem 'type' deve raise."""
    finding = _minimal_valid_finding()
    del finding["proposed_evolution"]["type"]
    with pytest.raises(QAFindingValidationError, match="proposed_evolution.type"):
        validate_qa_finding(finding)


def test_proposed_evolution_type_prefix():
    """proposed_evolution.type deve começar com 'qa-finding-'."""
    finding = _minimal_valid_finding()
    finding["proposed_evolution"]["type"] = "random-prefix-validator-claim"
    with pytest.raises(QAFindingValidationError, match="qa-finding-"):
        validate_qa_finding(finding)
