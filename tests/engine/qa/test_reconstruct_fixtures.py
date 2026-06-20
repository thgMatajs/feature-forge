"""Tests for engine.qa._reconstruct_fixtures_from_findings.

R8 cobre dois eixos do reconstruct de Fixtures a partir de findings
validator-claim:

  - Item 3: ``validator_path`` relativo resolve com precedência
    projeto > FORGE_HOME. Validators canon vivem em
    ``FORGE_HOME/validators/`` (não no projeto consumidor), então um
    basename nu deve cair no fallback FORGE_HOME quando o projeto não
    tem o arquivo. Validator local do projeto tem precedência.
  - Item 4: ``invocation_args`` declarado no evidence/finding é threado
    pra ``Fixture.extra_args`` (validators feature/task-scoped exigem
    ``--scope feature --id <slug>``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.qa import _reconstruct_fixtures_from_findings
from engine.qa.ingest import RunTree


def _run_tree(tmp_path: Path) -> RunTree:
    """Cria um RunTree mínimo dentro de tmp_path.

    O reconstruct só usa ``fixtures_dir``, mas o dataclass exige todos os
    campos — montamos uma tree completa apontando subdirs de tmp_path.
    """
    root = tmp_path
    root.mkdir(parents=True, exist_ok=True)
    fixtures_dir = root / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return RunTree(
        run_id="r-test",
        root=root,
        fixtures_dir=fixtures_dir,
        findings_dir=root / "findings",
        audit_dir=root / "audit",
        snapshot_dir=root / "snapshot",
    )


def _vc_finding(
    *,
    fixture_path: str = "fixtures/validator-claim-foo.yaml",
    validator_path: str,
    tree_rel_path: str = "src/Offending.kt",
    invocation_args=None,
) -> dict:
    ev: dict = {
        "fixture_path": fixture_path,
        "validator_path": validator_path,
        "tree_rel_path": tree_rel_path,
    }
    if invocation_args is not None:
        ev["invocation_args"] = invocation_args
    return {
        "vector": "validator-claim",
        "executable": True,
        "evidence": ev,
    }


# ---------------------------------------------------------------------------
# Item 3 — validator_path resolve via FORGE_HOME fallback (project-first)
# ---------------------------------------------------------------------------


def test_validator_path_falls_back_to_forge_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Basename nu que SÓ existe em FORGE_HOME/validators/ resolve lá.

    O projeto consumidor não tem o validator canon; o reconstruct deve
    cair no fallback ``forge_home()/validators/<name>``.
    """
    forge_home = tmp_path / "forge_home"
    (forge_home / "validators").mkdir(parents=True)
    canon = forge_home / "validators" / "validate_data_contract.py"
    canon.write_text("# canon validator\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_HOME", str(forge_home))

    project_root = tmp_path / "project"
    project_root.mkdir()
    run_tree = _run_tree(tmp_path / "run")

    findings = [_vc_finding(validator_path="validate_data_contract.py")]

    fixtures = _reconstruct_fixtures_from_findings(
        findings, run_tree, project_root=project_root
    )

    assert len(fixtures) == 1
    # Resolve pro path em FORGE_HOME/validators/, não pro project_root.
    assert fixtures[0].validator_path.resolve() == canon.resolve()


def test_validator_path_project_takes_precedence_over_forge_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validator local do projeto tem precedência sobre o de FORGE_HOME."""
    forge_home = tmp_path / "forge_home"
    (forge_home / "validators").mkdir(parents=True)
    (forge_home / "validators" / "validate_data_contract.py").write_text(
        "# forge home canon\n", encoding="utf-8"
    )
    monkeypatch.setenv("FORGE_HOME", str(forge_home))

    project_root = tmp_path / "project"
    (project_root / "validators").mkdir(parents=True)
    local = project_root / "validators" / "validate_data_contract.py"
    local.write_text("# project-local validator\n", encoding="utf-8")
    run_tree = _run_tree(tmp_path / "run")

    findings = [
        _vc_finding(validator_path="validators/validate_data_contract.py")
    ]

    fixtures = _reconstruct_fixtures_from_findings(
        findings, run_tree, project_root=project_root
    )

    assert len(fixtures) == 1
    # Project-first: resolve pro validator local, não pro FORGE_HOME.
    assert fixtures[0].validator_path.resolve() == local.resolve()


def test_validator_path_unresolvable_keeps_relative_under_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quando nem projeto nem FORGE_HOME têm o validator, comportamento
    atual é preservado (resolve sob project_root; sandbox vira error)."""
    forge_home = tmp_path / "forge_home"
    (forge_home / "validators").mkdir(parents=True)
    monkeypatch.setenv("FORGE_HOME", str(forge_home))

    project_root = tmp_path / "project"
    project_root.mkdir()
    run_tree = _run_tree(tmp_path / "run")

    findings = [_vc_finding(validator_path="validators/ghost.py")]

    fixtures = _reconstruct_fixtures_from_findings(
        findings, run_tree, project_root=project_root
    )

    assert len(fixtures) == 1
    # Sem invenção: resolve sob project_root (não vira FORGE_HOME nem absoluto).
    assert fixtures[0].validator_path == project_root / "validators" / "ghost.py"


# ---------------------------------------------------------------------------
# Item 4 — invocation_args threado pra Fixture.extra_args
# ---------------------------------------------------------------------------


def test_invocation_args_threaded_to_extra_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``invocation_args`` no evidence vira ``Fixture.extra_args``."""
    forge_home = tmp_path / "forge_home"
    (forge_home / "validators").mkdir(parents=True)
    (forge_home / "validators" / "validate_task_contract.py").write_text(
        "# canon\n", encoding="utf-8"
    )
    monkeypatch.setenv("FORGE_HOME", str(forge_home))

    project_root = tmp_path / "project"
    project_root.mkdir()
    run_tree = _run_tree(tmp_path / "run")

    findings = [
        _vc_finding(
            validator_path="validate_task_contract.py",
            invocation_args=["--scope", "feature", "--id", "foo"],
        )
    ]

    fixtures = _reconstruct_fixtures_from_findings(
        findings, run_tree, project_root=project_root
    )

    assert len(fixtures) == 1
    assert fixtures[0].extra_args == ["--scope", "feature", "--id", "foo"]


def test_invocation_args_absent_keeps_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem ``invocation_args`` → ``extra_args`` permanece None (compat)."""
    forge_home = tmp_path / "forge_home"
    (forge_home / "validators").mkdir(parents=True)
    (forge_home / "validators" / "v.py").write_text("# c\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_HOME", str(forge_home))

    project_root = tmp_path / "project"
    project_root.mkdir()
    run_tree = _run_tree(tmp_path / "run")

    findings = [_vc_finding(validator_path="v.py")]

    fixtures = _reconstruct_fixtures_from_findings(
        findings, run_tree, project_root=project_root
    )

    assert len(fixtures) == 1
    assert fixtures[0].extra_args is None


def test_invocation_args_non_list_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``invocation_args`` não-lista (LLM mal-formado) é ignorado → None."""
    forge_home = tmp_path / "forge_home"
    (forge_home / "validators").mkdir(parents=True)
    (forge_home / "validators" / "v.py").write_text("# c\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_HOME", str(forge_home))

    project_root = tmp_path / "project"
    project_root.mkdir()
    run_tree = _run_tree(tmp_path / "run")

    findings = [
        _vc_finding(validator_path="v.py", invocation_args="--scope feature")
    ]

    fixtures = _reconstruct_fixtures_from_findings(
        findings, run_tree, project_root=project_root
    )

    assert len(fixtures) == 1
    assert fixtures[0].extra_args is None
