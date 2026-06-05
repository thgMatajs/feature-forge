"""Tests for validators/validate_qa_report.py — schema-validates qa-report.json."""

from __future__ import annotations

import pytest

from validators.validate_qa_report import QAReportValidationError, validate_qa_report


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
