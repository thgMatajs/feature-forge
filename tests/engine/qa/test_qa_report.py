"""Tests for qa-report.json skeleton (Phase 0) + finalize (Phase 4).

CONF-001 (Wave 2 SDD gap closure): garante que ``run_qa`` escreve
``<run>/qa-report.json`` em Phase 0 com ``verdict="pending"`` e
finaliza in-place em Phase 4 preservando ``run.started_at`` /
``run.config_snapshot`` (audit trail).

Shape canonico: ``docs/schemas/qa-report.md`` (envelope nested).
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.qa import (
    _finalize_qa_report,
    _write_qa_report_skeleton,
    run_qa,
)
from engine.qa.ingest import QAConfig, create_run_tree
from engine.qa.scope import Scope
from engine.qa.synthesis import synthesize
from validators.validate_qa_report import validate_qa_report


def _make_feature_project(tmp_path: Path, slug: str) -> Path:
    """Cria layout minimo pra ``resolve_scope`` achar a feature."""
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


# ---------------------------------------------------------------------------
# Phase 0 skeleton
# ---------------------------------------------------------------------------


def test_phase0_writes_qa_report_skeleton(tmp_path: Path) -> None:
    """Phase 0 invoca ``run_qa`` (sem findings) -> qa-report.json existe
    com ``verdict='pending'`` + campos load-bearing presentes.
    """
    slug = "report-skeleton-feature"
    proj = _make_feature_project(tmp_path, slug)
    workflow_config = {"qa": {"enabled": True}}

    rc = run_qa(slug, project_root=proj, workflow_config=workflow_config)
    assert rc == 0

    qa_root = proj / ".planning" / "qa" / slug
    run_dirs = list(qa_root.iterdir())
    assert len(run_dirs) == 1, f"esperava 1 run dir, achei {len(run_dirs)}"
    report_path = run_dirs[0] / "qa-report.json"
    assert report_path.is_file(), "qa-report.json nao foi criado em Phase 0"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    # Schema doc requer envelope nested
    assert report["schema_version"] == 1
    assert report["verdict"] == "pending"
    assert "run" in report
    assert report["run"]["scope"]["type"] == "feature"
    assert report["run"]["scope"]["target"] == slug
    assert "started_at" in report["run"]
    assert report["run"]["started_at"].endswith("Z")
    assert "config_snapshot" in report["run"]
    assert "sandbox_budget_seconds_total" in report["run"]["config_snapshot"]
    assert isinstance(report["findings"], list)
    assert report["findings"] == []
    assert report["summary"]["total_findings"] == 0


def test_write_qa_report_skeleton_isolated(tmp_path: Path) -> None:
    """Chamada direta do helper produz shape canonico (sem dependencia
    do dispatch CLI)."""
    scope = Scope(type="feature", target="iso", paths=())
    tree = create_run_tree(scope, project_root=tmp_path)
    cfg = QAConfig()
    _write_qa_report_skeleton(scope, tree, cfg)

    payload = json.loads(
        (tree.root / "qa-report.json").read_text(encoding="utf-8")
    )
    assert payload["verdict"] == "pending"
    assert payload["run"]["id"] == tree.run_id
    assert payload["summary"] == {
        "total_findings": 0,
        "by_severity": {},
        "by_vector": {},
    }


# ---------------------------------------------------------------------------
# Phase 4 finalize
# ---------------------------------------------------------------------------


def test_phase4_finalizes_qa_report_verdict(tmp_path: Path) -> None:
    """Finalize substitui verdict/findings/summary preservando run.started_at
    e adiciona run.finished_at.
    """
    scope = Scope(type="feature", target="fin-feature", paths=())
    tree = create_run_tree(scope, project_root=tmp_path)
    cfg = QAConfig()
    _write_qa_report_skeleton(scope, tree, cfg)

    skeleton = json.loads(
        (tree.root / "qa-report.json").read_text(encoding="utf-8")
    )
    started_at = skeleton["run"]["started_at"]
    config_snapshot = skeleton["run"]["config_snapshot"]

    # Inject 1 critical finding -> BLOCK
    finding = {
        "vector": "validator-claim",
        "severity": "critical",
        "title": "demo",
        "description": "demo description",
        "scope": {"files": ["validators/x.py"]},
        "evidence": {"auditor": "demo-auditor"},
    }
    result = synthesize([finding])
    assert result.verdict == "BLOCK"

    _finalize_qa_report(tree, result)

    final = json.loads(
        (tree.root / "qa-report.json").read_text(encoding="utf-8")
    )
    assert final["verdict"] == "BLOCK"
    assert final["run"]["started_at"] == started_at, (
        "Phase 4 destruiu started_at — audit trail quebrado"
    )
    assert final["run"]["config_snapshot"] == config_snapshot, (
        "Phase 4 destruiu config_snapshot — audit trail quebrado"
    )
    assert "finished_at" in final["run"]
    assert final["run"]["finished_at"].endswith("Z")
    assert final["summary"]["total_findings"] == 1
    assert final["summary"]["by_severity"]["critical"] == 1
    assert final["summary"]["by_vector"].get("validator-claim") == 1
    assert len(final["findings"]) == 1


def _empty_synthesis_result():
    """SynthesisResult PASS vazio com todas as keys que validate_qa_report
    exige (by_severity 5 keys, by_vector 4 keys)."""
    return synthesize([])


def test_finalize_computes_duration_s(tmp_path: Path) -> None:
    """F-3: finalize escreve run.duration_s coerente (>=0) derivado de
    finished - started; validate_qa_report passa no report finalizado.
    """
    scope = Scope(type="feature", target="dur-feature", paths=())
    tree = create_run_tree(scope, project_root=tmp_path)
    cfg = QAConfig()
    _write_qa_report_skeleton(scope, tree, cfg)

    # Forca started_at num valor conhecido no passado pra duration ser > 0.
    report_path = tree.root / "qa-report.json"
    skeleton = json.loads(report_path.read_text(encoding="utf-8"))
    skeleton["run"]["started_at"] = "2026-06-19T12:00:00Z"
    report_path.write_text(
        json.dumps(skeleton, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    result = _empty_synthesis_result()
    _finalize_qa_report(tree, result)

    final = json.loads(report_path.read_text(encoding="utf-8"))
    assert "duration_s" in final["run"], "F-3: run.duration_s ausente"
    assert isinstance(final["run"]["duration_s"], (int, float))
    assert final["run"]["duration_s"] >= 0

    # validate_qa_report exige run.duration_s presente (L62) — nao deve raise.
    validate_qa_report(final)


def test_finalize_duration_s_graceful_when_started_missing(tmp_path: Path) -> None:
    """F-3: started_at ausente/malformado -> duration_s = 0.0 (degradacao
    graciosa, nao derruba finalize)."""
    scope = Scope(type="feature", target="dur-missing", paths=())
    tree = create_run_tree(scope, project_root=tmp_path)

    # Sem skeleton: finalize reconstroi envelope; started_at ausente.
    result = _empty_synthesis_result()
    _finalize_qa_report(tree, result)

    final = json.loads(
        (tree.root / "qa-report.json").read_text(encoding="utf-8")
    )
    assert final["run"]["duration_s"] == 0.0


def test_finalize_qa_report_tolerates_missing_skeleton(tmp_path: Path) -> None:
    """Se Phase 0 nao escreveu skeleton (disk error, caller fora de ordem),
    finalize reconstroi envelope basico em vez de raise."""
    scope = Scope(type="feature", target="missing-skel", paths=())
    tree = create_run_tree(scope, project_root=tmp_path)

    # NAO chamamos _write_qa_report_skeleton — file ausente
    assert not (tree.root / "qa-report.json").exists()

    result = synthesize([])
    _finalize_qa_report(tree, result)

    final = json.loads(
        (tree.root / "qa-report.json").read_text(encoding="utf-8")
    )
    assert final["verdict"] == "PASS"
    assert final["run"]["id"] == tree.run_id
    assert "finished_at" in final["run"]
