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


def _validator_claim_executable_draft(
    fixture_path: str, validator_path: str, tree_rel_path: str
) -> dict:
    """Draft validator-claim executável (reconstrói uma Fixture real)."""
    d = _validator_claim_draft(fixture_path)
    d["evidence"]["validator_path"] = validator_path
    d["evidence"]["tree_rel_path"] = tree_rel_path
    d["executable"] = True
    return d


@pytest.mark.integration
def test_stale_sandbox_results_rerun_when_checkpoint_below_phase_3(
    tmp_path: Path,
) -> None:
    """A3 (review pr27): sandbox-results.json existente mas checkpoint phase < 3
    é STALE — engine re-roda o sandbox em vez de confiar no arquivo.

    Cenário: crash após write parcial de sandbox-results.json, antes de
    synthesis. O resume não pode replay verbatim um arquivo de fase incompleta.
    """
    slug = "stale-feature"
    proj = _make_feature_project(tmp_path, slug)
    workflow_config = {"qa": {"enabled": True}}

    # Validator sintético no project/validators/ (root allowed pela A1) que
    # escaneia o mini-tree e sai 1 se achar Offending.kt.
    (proj / "validators").mkdir(parents=True)
    (proj / "validators" / "vc_validator.py").write_text(
        "import argparse, sys\n"
        "from pathlib import Path\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--project-root', required=True)\n"
        "args, _ = p.parse_known_args()\n"
        "hits = list(Path(args.project_root).rglob('Offending.kt'))\n"
        "sys.exit(1 if hits else 0)\n",
        encoding="utf-8",
    )

    scope = resolve_scope(slug, project_root=proj)
    rt = create_run_tree(scope, project_root=proj)

    # Materializa o mini-tree do contra-exemplo dentro de fixtures/<name>/.
    mini_tree = rt.fixtures_dir / "validator-claim-foo" / "src"
    mini_tree.mkdir(parents=True)
    (mini_tree / "Offending.kt").write_text("// offending\n", encoding="utf-8")

    draft = _validator_claim_executable_draft(
        fixture_path="fixtures/validator-claim-foo.yaml",
        validator_path="validators/vc_validator.py",
        tree_rel_path="src/Offending.kt",
    )
    (rt.findings_dir / "validator-claim.json").write_text(
        json.dumps({"findings": [draft]}), encoding="utf-8"
    )

    # sandbox-results.json STALE: entrada que NÃO corresponde a nenhuma fixture
    # atual (basename inventado) — simula write de fase incompleta.
    (rt.root / "sandbox-results.json").write_text(
        json.dumps(
            [{"fixture_name": "STALE-GHOST", "status": "ok", "exit_code": 0}]
        ),
        encoding="utf-8",
    )

    from engine.qa import _write_qa_report_skeleton

    _write_qa_report_skeleton(scope, rt, QAConfig())
    # Checkpoint phase 0 (< 3): sandbox NÃO completou — o arquivo é stale.
    write_checkpoint(
        rt.root,
        run_id=rt.run_id,
        scope_type=scope.type,
        scope_target=scope.target,
        last_phase_completed=0,
        findings_partial_count=1,
    )

    run_qa(slug, project_root=proj, workflow_config=workflow_config)

    # O engine re-rodou: a entrada STALE-GHOST sumiu, e a fixture real
    # (validator-claim-foo) aparece no sandbox-results regenerado.
    results = json.loads(
        (rt.root / "sandbox-results.json").read_text(encoding="utf-8")
    )
    names = {r.get("fixture_name") for r in results}
    assert "STALE-GHOST" not in names, "engine confiou no sandbox-results stale"
    assert "validator-claim-foo" in names, "engine não re-rodou o sandbox"


@pytest.mark.integration
def test_unresolvable_validator_claim_surfaces_finding_not_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A4 (review pr27): validator-claim com validator irresolvível →
    finding surfaced (não false-clean) + warning em stderr.

    O validator declarado mora num root allowed (project/validators/) mas o
    arquivo NÃO existe → run_sandbox devolve status=error. Antes isso era
    dropado → report 'clean' pro vetor 'validator que mente'. Agora deriva
    um finding medium e avisa em stderr.
    """
    slug = "unresolvable-feature"
    proj = _make_feature_project(tmp_path, slug)
    workflow_config = {"qa": {"enabled": True}}

    # project/validators/ existe (root allowed pela A1), mas o validator
    # declarado (ghost.py) NÃO existe → status=error em run_sandbox.
    (proj / "validators").mkdir(parents=True)

    scope = resolve_scope(slug, project_root=proj)
    rt = create_run_tree(scope, project_root=proj)

    # Mini-tree materializado (input precisa resolver dentro do sandbox).
    mini_tree = rt.fixtures_dir / "validator-claim-ghost" / "src"
    mini_tree.mkdir(parents=True)
    (mini_tree / "Offending.kt").write_text("// x\n", encoding="utf-8")

    draft = _validator_claim_executable_draft(
        fixture_path="fixtures/validator-claim-ghost.yaml",
        validator_path="validators/ghost.py",  # dentro do root allowed, inexistente
        tree_rel_path="src/Offending.kt",
    )
    (rt.findings_dir / "validator-claim.json").write_text(
        json.dumps({"findings": [draft]}), encoding="utf-8"
    )

    from engine.qa import _write_qa_report_skeleton

    _write_qa_report_skeleton(scope, rt, QAConfig())
    write_checkpoint(
        rt.root,
        run_id=rt.run_id,
        scope_type=scope.type,
        scope_target=scope.target,
        last_phase_completed=0,
        findings_partial_count=1,
    )

    run_qa(slug, project_root=proj, workflow_config=workflow_config)

    final = json.loads((rt.root / "qa-report.json").read_text(encoding="utf-8"))
    vectors = {f.get("vector") for f in final["findings"]}
    assert "validator-claim-unresolvable" in vectors, (
        f"validator irresolvível não foi surfaced — false-clean; "
        f"vetores={vectors}"
    )
    # Não settla clean (há finding) e stderr avisa.
    captured = capsys.readouterr()
    assert "irresolvível" in captured.err
