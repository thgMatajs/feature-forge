"""Tests for run_qa checkpoint auto-resume — F-2 (resume flagless).

Veredito do mantenedor (Decisão 10 / row 32 — zero flags): o resume de
``forge qa`` é via **checkpoint auto-resume**, sem flag CLI nem positional
novo. A maquinaria estende a Decisão 27 (pause/resume):

- Phase 0 (e fronteiras de phase) ESCREVEM um checkpoint da run em andamento.
- Re-invocar ``run_qa(target)`` PURO (mesmo argv) reata a run em andamento
  via ``find_resumable_run`` — sem criar run nova.
- Na CONCLUSÃO (Phase 5 emit), o checkpoint é LIMPO (senão a run fica
  "presa em resume" — mesma classe do P-17). [M-002 do plan-auditor]

Inferência de phase (lida do flow real):
- findings/*.json ausentes → Phase 1-2 pendente: handoff escrito, devolve
  controle pro conductor (return 0).
- findings/*.json presentes E sandbox-results.json AUSENTE → Phase 3
  (sandbox handshake): segue o caminho synthesis→emit com os findings que tem.
- qa-report.json verdict != pending → Phase 5 (emit idempotente).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.qa import run_qa
from engine.qa.checkpoint import read_checkpoint
from engine.qa.scope import resolve_scope


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


def _qa_run_dirs(proj: Path, slug: str) -> list[Path]:
    """Lista os run dirs sob .planning/qa/<target>/ (cada um é uma run)."""
    scope = resolve_scope(slug, project_root=proj)
    from engine.qa.ingest import sanitize_scope_target

    safe = sanitize_scope_target(scope.target)
    assert safe is not None
    scope_dir = proj / ".planning" / "qa" / safe
    if not scope_dir.is_dir():
        return []
    return sorted(d for d in scope_dir.iterdir() if d.is_dir())


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


# ---------------------------------------------------------------------------
# B.2 — checkpoint nas fronteiras de phase: re-invoke puro reata
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reinvoke_resumes_via_checkpoint(tmp_path: Path) -> None:
    """Phase 0 escreve checkpoint; re-invocar `run_qa(target)` puro NÃO cria
    run nova — reata a mesma run-id via find_resumable_run."""
    slug = "resume-feature"
    proj = _make_feature_project(tmp_path, slug)
    wf = {"qa": {"enabled": True}}

    # Primeira invocação: Phase 0 roda (sem findings → handoff + return 0).
    rc1 = run_qa(slug, project_root=proj, workflow_config=wf)
    assert rc1 == 0

    runs_after_first = _qa_run_dirs(proj, slug)
    assert len(runs_after_first) == 1, "Phase 0 deveria criar exatamente 1 run"
    run_dir = runs_after_first[0]

    # B.2: checkpoint escrito na fronteira de Phase 0 (não só em SIGINT).
    cp = read_checkpoint(run_dir)
    assert cp is not None, "checkpoint deveria existir após Phase 0 (B.2)"
    assert cp.run_id == run_dir.name

    # Re-invocação PURA (mesmo argv): reata via checkpoint, sem criar run nova.
    rc2 = run_qa(slug, project_root=proj, workflow_config=wf)
    assert rc2 == 0

    runs_after_second = _qa_run_dirs(proj, slug)
    assert len(runs_after_second) == 1, (
        "re-invoke puro NÃO deveria criar run nova — deveria reatar"
    )
    assert runs_after_second[0].name == run_dir.name, "reata a mesma run-id"


# ---------------------------------------------------------------------------
# M-002 — checkpoint limpo na conclusão (Phase 5)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_checkpoint_cleared_on_completion(tmp_path: Path) -> None:
    """Após Phase 5 (verdict emitido), o checkpoint não existe; re-invocar
    puro cria run NOVA (não fica preso reatando a run concluída). [M-002]"""
    slug = "complete-feature"
    proj = _make_feature_project(tmp_path, slug)
    wf = {"qa": {"enabled": True}}

    # 1ª invocação — Phase 0 (escreve checkpoint, sem findings).
    run_qa(slug, project_root=proj, workflow_config=wf)
    runs = _qa_run_dirs(proj, slug)
    assert len(runs) == 1
    run_dir = runs[0]
    assert read_checkpoint(run_dir) is not None

    # Conductor escreve findings → 2ª invocação reata e completa (Phase 4/5).
    (run_dir / "findings" / "validator-claim.json").write_text(
        json.dumps(
            {"findings": [_validator_claim_draft("fixtures/validator-claim-foo.yaml")]}
        ),
        encoding="utf-8",
    )
    rc = run_qa(slug, project_root=proj, workflow_config=wf)
    assert rc in (0, 1)  # FLAG/PASS → 0; BLOCK → 1

    # M-002: verdict emitido → checkpoint LIMPO.
    report = json.loads((run_dir / "qa-report.json").read_text(encoding="utf-8"))
    assert report["verdict"] != "pending", "Phase 5 deveria emitir verdict final"
    assert read_checkpoint(run_dir) is None, (
        "M-002: checkpoint deveria estar limpo após conclusão (Phase 5)"
    )

    # Re-invocar puro NÃO reata a run concluída — começa run NOVA.
    run_qa(slug, project_root=proj, workflow_config=wf)
    runs_after = _qa_run_dirs(proj, slug)
    assert len(runs_after) == 2, (
        "M-002: run concluída não deve ser reatada; re-invoke cria run nova"
    )


# ---------------------------------------------------------------------------
# B.1 — inferência de phase no resume
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_resume_infers_phase3_with_findings_no_sandbox(tmp_path: Path) -> None:
    """findings presentes E sandbox-results AUSENTE: re-invoke reata e segue
    o caminho synthesis→emit (Phase 3+) sem criar run nova."""
    slug = "phase3-feature"
    proj = _make_feature_project(tmp_path, slug)
    wf = {"qa": {"enabled": True}}

    run_qa(slug, project_root=proj, workflow_config=wf)
    run_dir = _qa_run_dirs(proj, slug)[0]

    # Conductor escreveu findings, MAS ainda não escreveu sandbox-results.json.
    (run_dir / "findings" / "validator-claim.json").write_text(
        json.dumps(
            {"findings": [_validator_claim_draft("fixtures/validator-claim-foo.yaml")]}
        ),
        encoding="utf-8",
    )
    assert not (run_dir / "sandbox-results.json").exists()

    rc = run_qa(slug, project_root=proj, workflow_config=wf)
    assert rc in (0, 1)

    # Não criou run nova; synthesis rodou (verdict deixou de ser pending).
    assert len(_qa_run_dirs(proj, slug)) == 1
    report = json.loads((run_dir / "qa-report.json").read_text(encoding="utf-8"))
    assert report["verdict"] != "pending"


@pytest.mark.integration
def test_resume_phase5_emit_is_idempotent(tmp_path: Path) -> None:
    """Phase 5 emit é idempotente: reatar uma run pendente com findings +
    sandbox-results e re-emitir produz o MESMO verdict, sem criar run nova.

    Nota de design (find_resumable_run): uma run só é resumível enquanto
    ``qa-report.json`` tem verdict=pending. Quando o synthesis→emit roda no
    resume, ele settla o verdict E limpa o checkpoint (M-002) — a run deixa
    de ser resumível, por contrato. Pra exercitar a idempotência do emit
    (rodar o caminho synthesis→emit duas vezes sobre o mesmo estado),
    re-semeamos o estado pendente (skeleton pending + checkpoint Phase 0)
    entre as duas invocações; o verdict resultante deve ser idêntico."""
    from engine.qa import _write_qa_report_skeleton
    from engine.qa.checkpoint import write_checkpoint
    from engine.qa.ingest import QAConfig

    slug = "phase5-feature"
    proj = _make_feature_project(tmp_path, slug)
    wf = {"qa": {"enabled": True}}

    # Phase 0 (escreve checkpoint), depois conductor escreve findings +
    # sandbox-results (Phase 3 done, verdict ainda pending).
    run_qa(slug, project_root=proj, workflow_config=wf)
    scope = resolve_scope(slug, project_root=proj)
    run_dir = _qa_run_dirs(proj, slug)[0]
    (run_dir / "findings" / "validator-claim.json").write_text(
        json.dumps(
            {"findings": [_validator_claim_draft("fixtures/validator-claim-foo.yaml")]}
        ),
        encoding="utf-8",
    )
    (run_dir / "sandbox-results.json").write_text(
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

    # Re-invoke #1 (puro): reata via checkpoint pending → synthesis→emit.
    rc1 = run_qa(slug, project_root=proj, workflow_config=wf)
    assert rc1 in (0, 1)
    assert len(_qa_run_dirs(proj, slug)) == 1, "resume não cria run nova"
    report1 = json.loads((run_dir / "qa-report.json").read_text(encoding="utf-8"))
    settled = report1["verdict"]
    assert settled != "pending", "synthesis→emit settla o verdict"
    # M-002: emit limpou o checkpoint na conclusão.
    assert read_checkpoint(run_dir) is None

    # Re-semeia estado pendente (skeleton pending + checkpoint Phase 0) pra
    # rodar o caminho de emit de novo sobre o mesmo input.
    from engine.qa import _reattach_run_tree

    reseed_tree = _reattach_run_tree(run_dir, None)  # type: ignore[arg-type]
    _write_qa_report_skeleton(scope, reseed_tree, QAConfig())
    write_checkpoint(
        run_dir,
        run_id=run_dir.name,
        scope_type=scope.type,
        scope_target=scope.target,
        last_phase_completed=0,
        findings_partial_count=1,
    )

    # Re-invoke #2 (puro): reata de novo e re-emite — verdict idêntico.
    rc2 = run_qa(slug, project_root=proj, workflow_config=wf)
    assert rc2 in (0, 1)
    assert len(_qa_run_dirs(proj, slug)) == 1
    report2 = json.loads((run_dir / "qa-report.json").read_text(encoding="utf-8"))
    assert report2["verdict"] == settled, "emit idempotente preserva verdict"
    assert read_checkpoint(run_dir) is None
