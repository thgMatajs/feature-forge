"""Tests for validators/validate_qa_report.py — schema-validates qa-report.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from validators.validate_qa_report import QAReportValidationError, validate_qa_report

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / "templates" / "qa-report.template.json"


def test_template_rules_align_with_validator_enums():
    """C-42q (PR22-R-003): as regras do template citam os MESMOS enums que o
    validator aceita — antes diziam verdict ∈ PASS|FAIL e scope.type ∈
    feature|task|full, que o validator rejeita.
    """
    raw = _TEMPLATE.read_text(encoding="utf-8")
    data = json.loads(raw)
    rules = " ".join(data["_template_rules"])
    # verdict canônico
    assert "BLOCK" in rules and "FLAG" in rules and "PASS" in rules
    assert "FAIL" not in rules, "verdict FAIL não existe no validator"
    # scope.type canônico
    assert "screen" in rules and "paranoid" in rules
    assert "full" not in rules, "scope.type 'full' não existe no validator"


def test_template_filled_passes_validator():
    """Smoke: preencher os {{...}} com valores válidos + strip _* → validate OK."""
    raw = _TEMPLATE.read_text(encoding="utf-8")
    filled = (
        raw.replace("{{run_id}}", "2026-06-18T10-00-00Z-abcd")
        .replace("{{scope_type}}", "feature")
        .replace("{{scope_target}}", "lembrete-rega")
        .replace("{{started_at}}", "2026-06-18T10:00:00Z")
    )
    data = json.loads(filled)
    # finished_at/duration vazios no template — preencher pra um run real.
    data["run"]["finished_at"] = "2026-06-18T10:03:00Z"
    data["run"]["duration_s"] = 180
    # Strip chaves-guia _* (o artefato canônico não as carrega).
    data = {k: v for k, v in data.items() if not k.startswith("_")}
    validate_qa_report(data)  # no raise


def _minimal_valid_report() -> dict:
    return {
        "schema_version": 1,
        "run": {
            "id": "2026-06-05T14-32-08Z-a1b2",
            "scope": {"type": "feature", "target": "lembrete-rega"},
            "config_snapshot": {},
            "started_at": "2026-06-05T14:32:08Z",
            "finished_at": "2026-06-05T14:35:22Z",
            "duration_s": 194,
        },
        "verdict": "PASS",
        "summary": {
            "total_findings": 0,
            "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "by_vector": {"spec-vs-spec": 0, "coverage": 0, "chaos": 0, "validator-claim": 0},
        },
        "findings": [],
    }


def test_happy_path_validates():
    validate_qa_report(_minimal_valid_report())  # no raise


def test_missing_required_field_fails():
    report = _minimal_valid_report()
    del report["verdict"]
    with pytest.raises(QAReportValidationError, match="verdict"):
        validate_qa_report(report)


def test_schema_version_drift_fails():
    report = _minimal_valid_report()
    report["schema_version"] = 2
    with pytest.raises(QAReportValidationError, match="schema_version"):
        validate_qa_report(report)


def test_verdict_enum_strict():
    report = _minimal_valid_report()
    report["verdict"] = "MAYBE"
    with pytest.raises(QAReportValidationError, match="verdict"):
        validate_qa_report(report)


def test_by_severity_sum_must_match_total():
    report = _minimal_valid_report()
    report["summary"]["total_findings"] = 5
    # by_severity sum is 0, mismatch
    with pytest.raises(QAReportValidationError, match="total_findings"):
        validate_qa_report(report)


def test_scope_must_be_dict_not_string():
    """Regression for HI-01: run.scope=string deve raise QAReportValidationError, não AttributeError."""
    report = _minimal_valid_report()
    report["run"]["scope"] = "feature"  # string em vez de dict
    with pytest.raises(QAReportValidationError, match="run.scope"):
        validate_qa_report(report)


def test_findings_count_must_match_total_findings():
    """Regression for HI-02: len(findings) precisa bater com summary.total_findings.

    Cenário: total_findings=0 e by_severity zerado (cross-check com by_severity passa),
    mas findings tem 1 entry. Cross-check len(findings) vs total_findings deve raise.
    """
    report = _minimal_valid_report()
    report["findings"] = [
        {"id": "F-001", "severity": "info", "title": "ghost finding"}
    ]
    # total_findings ainda é 0; by_severity ainda soma 0; só len(findings) discorda
    with pytest.raises(QAReportValidationError, match="findings"):
        validate_qa_report(report)


def test_findings_must_be_list_not_string():
    """Regression for HI-03: findings=string deve raise QAReportValidationError."""
    report = _minimal_valid_report()
    report["findings"] = "vazio"  # string em vez de list
    with pytest.raises(QAReportValidationError, match="findings"):
        validate_qa_report(report)


def test_summary_must_be_dict():
    """ME-01: summary não-dict (string) deve raise QAReportValidationError, não AttributeError."""
    report = _minimal_valid_report()
    report["summary"] = "vazio"  # string em vez de dict
    with pytest.raises(QAReportValidationError, match="summary"):
        validate_qa_report(report)


def test_total_findings_missing_fails():
    """ME-02: ausência de summary.total_findings não pode ser inferida como 0."""
    report = _minimal_valid_report()
    del report["summary"]["total_findings"]
    with pytest.raises(QAReportValidationError, match="total_findings"):
        validate_qa_report(report)


def test_total_findings_must_be_int():
    """ME-02: summary.total_findings precisa ser int, não string."""
    report = _minimal_valid_report()
    report["summary"]["total_findings"] = "0"  # string em vez de int
    with pytest.raises(QAReportValidationError, match="total_findings"):
        validate_qa_report(report)


def test_by_severity_values_must_be_int():
    """ME-03: by_severity[k] precisa ser int, não string."""
    report = _minimal_valid_report()
    report["summary"]["by_severity"]["critical"] = "1"  # string em vez de int
    with pytest.raises(QAReportValidationError, match="by_severity"):
        validate_qa_report(report)


def test_run_config_snapshot_required():
    """ME-04: run.config_snapshot é required (load-bearing pra reprodução de veredito)."""
    report = _minimal_valid_report()
    del report["run"]["config_snapshot"]
    with pytest.raises(QAReportValidationError, match="config_snapshot"):
        validate_qa_report(report)


def test_scope_type_invalid_enum():
    """ME-05: run.scope.type fora do enum {feature, screen, task, paranoid} deve raise."""
    report = _minimal_valid_report()
    report["run"]["scope"]["type"] = "global"  # fora do enum
    with pytest.raises(QAReportValidationError, match="scope.type"):
        validate_qa_report(report)


def test_by_severity_missing_key():
    """ME-05: by_severity sem 'critical' deve raise — keys obrigatórias completas."""
    report = _minimal_valid_report()
    del report["summary"]["by_severity"]["critical"]
    with pytest.raises(QAReportValidationError, match="by_severity"):
        validate_qa_report(report)


def test_by_vector_missing_required_key():
    """ME-05: by_vector sem 'chaos' deve raise — subset _REQUIRED_VECTOR_KEYS exigido."""
    report = _minimal_valid_report()
    del report["summary"]["by_vector"]["chaos"]
    with pytest.raises(QAReportValidationError, match="by_vector"):
        validate_qa_report(report)


def test_run_id_format_invalid():
    """LO-01: run.id fora do regex YYYY-MM-DDTHH-MM-SSZ-<4hex> deve raise."""
    report = _minimal_valid_report()
    report["run"]["id"] = "not-a-valid-id"
    with pytest.raises(QAReportValidationError, match="run.id"):
        validate_qa_report(report)
