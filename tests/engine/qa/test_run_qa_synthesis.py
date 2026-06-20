"""Tests for run_qa synthesis wiring — F-4 (hidrata sandbox_result).

Integração: monta uma run tree resumível (checkpoint + qa-report pending +
findings + sandbox-results), re-invoca ``run_qa`` e confirma que o finding
validator-claim chega ao ``qa-report.json`` final com
``evidence.sandbox_result`` hidratado. ``validate_qa_report`` (que valida
cada finding via ``validate_qa_finding``) não deve raise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.qa import run_qa
from engine.qa.checkpoint import write_checkpoint
from engine.qa.ingest import QAConfig, create_run_tree
from engine.qa.scope import Scope, resolve_scope
from validators.validate_qa_report import validate_qa_report


def _make_feature_project(tmp_path: Path, slug: str) -> Path:
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    feature_dir = (
        proj / "docs" / "feature-implementation-workflow" / "features" / slug
    )
    feature_dir.mkdir(parents=True)
    (feature_dir / "feature-spec.yaml").write_text(
        f"schema-version: 1\nslug: {slug}\n", encoding="utf-8"
    )
    return proj


def _validator_claim_draft(fixture_path: str) -> dict:
    return {
        "id": "vc-0001",
        "fingerprint": "a" * 64,
        "vector": "validator-claim",
        "severity": "high",
        "title": "validator que mente",
        "description": "validator forge nao detecta o caso",
        "scope": {"files": ["validators/x.py"]},
        "evidence": {
            "auditor": "qa-auditor-validator-claim",
            "auditor_reasoning": "deveria pegar mas nao pegou",
            "fixture_path": fixture_path,
            "sandbox_result": None,
        },
        "proposed_evolution": {
            "type": "qa-finding-validator-claim",
            "summary": "endurecer o validator",
            "actionable": True,
        },
        "created_at": "2026-06-19T12:00:00Z",
    }


@pytest.mark.integration
def test_validator_claim_evidence_hydrated_in_report(tmp_path: Path) -> None:
    """F-4 wire: run_qa hidrata evidence.sandbox_result do draft
    validator-claim a partir de sandbox-results.json; report final passa
    validate_qa_report."""
    slug = "hydrate-feature"
    proj = _make_feature_project(tmp_path, slug)
    workflow_config = {"qa": {"enabled": True}}

    scope = resolve_scope(slug, project_root=proj)
    rt = create_run_tree(scope, project_root=proj)

    # findings/*.json — 1 draft validator-claim com sandbox_result=null
    (rt.findings_dir / "validator-claim.json").write_text(
        json.dumps(
            {"findings": [_validator_claim_draft("fixtures/validator-claim-foo.yaml")]}
        ),
        encoding="utf-8",
    )

    # sandbox-results.json — stub com exit_code int casando por basename
    (rt.root / "sandbox-results.json").write_text(
        json.dumps(
            [
                {
                    "fixture_name": "validator-claim-foo",
                    "status": "ok",
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                    "duration_s": 0.2,
                }
            ]
        ),
        encoding="utf-8",
    )

    # skeleton qa-report.json pending + checkpoint → run resumível.
    from engine.qa import _write_qa_report_skeleton

    _write_qa_report_skeleton(scope, rt, QAConfig())
    write_checkpoint(
        rt.root,
        run_id=rt.run_id,
        scope_type=scope.type,
        scope_target=scope.target,
        last_phase_completed=2,
        findings_partial_count=1,
    )

    rc = run_qa(slug, project_root=proj, workflow_config=workflow_config)
    assert rc in (0, 1)  # FLAG/PASS -> 0; high>=3 nao aplica, single high -> FLAG/0

    final = json.loads((rt.root / "qa-report.json").read_text(encoding="utf-8"))
    vc = [f for f in final["findings"] if f.get("vector") == "validator-claim"]
    assert vc, "finding validator-claim ausente no report final"
    sr = vc[0]["evidence"]["sandbox_result"]
    assert isinstance(sr, dict), "F-4: sandbox_result deveria estar hidratado"
    assert sr["exit_code"] == 0

    validate_qa_report(final)
