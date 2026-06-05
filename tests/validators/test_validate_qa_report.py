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
