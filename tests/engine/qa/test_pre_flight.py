"""Tests for engine.qa.ingest — Phase 0 ingest (parse_qa_config + create_run_tree).

Cobre 3 casos canonicos (TDD) + 3 defensive:

- defaults aplicados quando section qa: ausente
- valores custom batem com workflow-config declarado
- inconsistencia enabled=false + auto-run=true vira warning (nao raise)
- defensive: None como input nao crasha
- create_run_tree cria os 4 subdirs (fixtures/findings/audit/snapshot)
- create_run_tree e idempotente (segunda chamada nao raise)

Spec §6.4 e §5.0. Consumer canonico: engine/qa.py top-level handler (Task 4.1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.qa.ingest import (
    QAConfig,
    RunTree,
    create_run_tree,
    parse_qa_config,
)
from engine.qa.scope import Scope


# ---------------------------------------------------------------------------
# parse_qa_config
# ---------------------------------------------------------------------------


def test_parse_qa_config_returns_defaults_when_section_absent() -> None:
    """Section qa: ausente -> QAConfig com defaults canonicos (spec §6.4)."""
    cfg = parse_qa_config({})

    assert isinstance(cfg, QAConfig)
    assert cfg.enabled is True
    assert cfg.auto_run_on_feature_done is False
    assert cfg.sandbox_budget_seconds_total == 60.0
    assert cfg.agent_timeout_seconds == 15.0
    assert cfg.paranoid_max_features == 10
    assert cfg.extensions_disabled == ()
    assert cfg.retention_days == 14
    assert cfg.warnings == []


def test_parse_qa_config_uses_custom_values_when_declared() -> None:
    """Valores declarados em workflow-config sobrescrevem defaults."""
    workflow_config = {
        "qa": {
            "enabled": True,
            "auto-run-on-feature-done": True,
            "sandbox-budget-seconds-total": 120,
            "agent-timeout-seconds": 30,
            "scope-defaults": {"paranoid-max-features": 5},
            "extensions": {"disabled": ["check-style", "check-format"]},
            "retention-days": 30,
        }
    }

    cfg = parse_qa_config(workflow_config)

    assert cfg.enabled is True
    assert cfg.auto_run_on_feature_done is True
    assert cfg.sandbox_budget_seconds_total == 120.0
    assert cfg.agent_timeout_seconds == 30.0
    assert cfg.paranoid_max_features == 5
    assert cfg.extensions_disabled == ("check-style", "check-format")
    assert cfg.retention_days == 30
    # enabled=true + auto-run=true e coerente -> sem warning
    assert cfg.warnings == []


def test_parse_qa_config_inconsistency_warning() -> None:
    """enabled=false + auto-run=true gera warning em cfg.warnings (nao raise).

    Caller (engine/qa.py Phase 0) decide se loga, propaga, ou ignora.
    """
    workflow_config = {
        "qa": {
            "enabled": False,
            "auto-run-on-feature-done": True,
        }
    }

    cfg = parse_qa_config(workflow_config)

    assert cfg.enabled is False
    assert cfg.auto_run_on_feature_done is True
    assert len(cfg.warnings) == 1
    assert "auto-run nunca dispara" in cfg.warnings[0]


# ---------------------------------------------------------------------------
# Defensive: None input
# ---------------------------------------------------------------------------


def test_parse_qa_config_none_input() -> None:
    """``parse_qa_config(None)`` trata None como dict vazio -> defaults.

    Consumer pode passar None quando workflow-config ainda nao foi lido;
    nao queremos AttributeError vazar — silenciamos e aplicamos defaults.
    """
    cfg = parse_qa_config(None)  # type: ignore[arg-type]

    assert cfg.enabled is True
    assert cfg.auto_run_on_feature_done is False
    assert cfg.warnings == []


# ---------------------------------------------------------------------------
# create_run_tree
# ---------------------------------------------------------------------------


def _make_scope() -> Scope:
    """Scope sintetico minimal — type/target/paths sao o suficiente."""
    return Scope(type="feature", target="example-feature", paths=())


def test_create_run_tree_creates_4_subdirs(tmp_path: Path) -> None:
    """Tree completa: fixtures + findings + audit + snapshot, todos criados."""
    scope = _make_scope()

    tree = create_run_tree(scope, project_root=tmp_path)

    assert isinstance(tree, RunTree)
    assert tree.root.exists() and tree.root.is_dir()
    assert tree.fixtures_dir.exists() and tree.fixtures_dir.name == "fixtures"
    assert tree.findings_dir.exists() and tree.findings_dir.name == "findings"
    assert tree.audit_dir.exists() and tree.audit_dir.name == "audit"
    assert tree.snapshot_dir.exists() and tree.snapshot_dir.name == "snapshot"
    # root e .planning/qa/<feature-slug>/<run-id>/
    assert tree.root.parent.name == "example-feature"
    assert tree.root.parent.parent.name == "qa"
    assert tree.root.parent.parent.parent.name == ".planning"


def test_create_run_tree_idempotent(tmp_path: Path) -> None:
    """Segunda chamada com mesmo scope nao raise (exist_ok=True).

    Run_id muda entre chamadas (CSPRNG suffix), mas o pattern de criacao
    deve tolerar diretorios pre-existentes — defensive contra retry.
    """
    scope = _make_scope()
    tree1 = create_run_tree(scope, project_root=tmp_path)

    # Forca o caso: cria um run_id arbitrario manualmente e re-invoca
    # (mesmo que run_id mude, os parents .planning/qa/<slug>/ existem).
    tree2 = create_run_tree(scope, project_root=tmp_path)

    # Ambos validos, ambos parents .planning/qa/<slug>/ pre-existentes
    # nao causaram erro.
    assert tree1.root != tree2.root  # run_id diferente
    assert tree1.fixtures_dir.exists()
    assert tree2.fixtures_dir.exists()


# ---------------------------------------------------------------------------
# Sanity: pre-existing dir nao quebra (defesa explicita do exist_ok)
# ---------------------------------------------------------------------------


def test_create_run_tree_tolerates_pre_existing_subdir(tmp_path: Path) -> None:
    """Subdir pre-existente nao raise — confirma exist_ok=True na pratica."""
    scope = _make_scope()
    # Pre-cria o parent path que o create_run_tree vai querer construir
    pre = tmp_path / ".planning" / "qa" / "example-feature"
    pre.mkdir(parents=True)

    tree = create_run_tree(scope, project_root=tmp_path)

    assert tree.root.exists()
    assert tree.fixtures_dir.exists()
