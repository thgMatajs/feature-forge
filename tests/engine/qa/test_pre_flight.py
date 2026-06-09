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


# ---------------------------------------------------------------------------
# FIX-8: parse_qa_config tolera tipos errados (string em vez de numero)
# ---------------------------------------------------------------------------


def test_parse_qa_config_string_budget_emits_warning_and_uses_default() -> None:
    """YAML com `sandbox-budget-seconds-total: "abc"` (string nao-castavel)
    nao deve raise ValueError — emite warning mentor-calmo e mantem default."""
    workflow_config = {
        "qa": {
            "enabled": True,
            "sandbox-budget-seconds-total": "abc",
        }
    }
    cfg = parse_qa_config(workflow_config)

    assert cfg.sandbox_budget_seconds_total == 60.0  # default preservado
    assert any("sandbox-budget-seconds-total" in w for w in cfg.warnings), (
        f"esperava warning sobre cast, obtive {cfg.warnings!r}"
    )


def test_parse_qa_config_string_agent_timeout_emits_warning() -> None:
    """`agent-timeout-seconds: "fast"` -> warning + default 15.0."""
    workflow_config = {"qa": {"agent-timeout-seconds": "fast"}}
    cfg = parse_qa_config(workflow_config)

    assert cfg.agent_timeout_seconds == 15.0
    assert any("agent-timeout-seconds" in w for w in cfg.warnings)


def test_parse_qa_config_string_paranoid_max_emits_warning() -> None:
    """`paranoid-max-features: "many"` -> warning + default 10."""
    workflow_config = {
        "qa": {"scope-defaults": {"paranoid-max-features": "many"}}
    }
    cfg = parse_qa_config(workflow_config)

    assert cfg.paranoid_max_features == 10
    assert any("paranoid-max-features" in w for w in cfg.warnings)


def test_parse_qa_config_string_retention_emits_warning() -> None:
    """`retention-days: "forever"` -> warning + default 14."""
    workflow_config = {"qa": {"retention-days": "forever"}}
    cfg = parse_qa_config(workflow_config)

    assert cfg.retention_days == 14
    assert any("retention-days" in w for w in cfg.warnings)


# ---------------------------------------------------------------------------
# FIX-9: create_run_tree sanitiza scope.target contra path traversal
# ---------------------------------------------------------------------------


def test_create_run_tree_sanitizes_path_traversal_in_target(tmp_path: Path) -> None:
    """scope.target com '../' nao deve criar dirs fora de .planning/qa/.

    Sanitizacao whitelist-based substitui qualquer char fora de [A-Za-z0-9._-]
    por '_'. Path separators ('/') somem; dots literais sobrevivem como
    parte do nome do componente (sao chars seguros num filename). A
    propriedade load-bearing e: NENHUM componente apos sanitize cria um
    novo nivel de diretorio (sem '/'), portanto resolve(tree.root) fica
    confinado a tmp_path/.planning/qa/.
    """
    malicious_scope = Scope(
        type="task", target="TASK-../../escape", paths=()
    )
    tree = create_run_tree(malicious_scope, project_root=tmp_path)

    # Garante que nada vazou pra fora de tmp_path apos resolve simbolico
    resolved = tree.root.resolve()
    assert str(resolved).startswith(str(tmp_path.resolve())), (
        f"path traversal escapou: {resolved!r}"
    )
    # Sanitizado deve continuar sob .planning/qa/<safe>
    assert ".planning/qa" in str(tree.root)
    # Componente do target sanitizado nao deve conter SEPARATORS ('/')
    # nem ser interpretado como traversal pelo filesystem.
    target_component = tree.root.parent.name
    assert "/" not in target_component
    # Path '..' como componente inteiro seria traversal; aqui o '..'
    # aparece embutido num nome maior ("TASK-.._.._escape"), que e tratado
    # pelo filesystem como um filename literal — nao volta um nivel.
    assert target_component != ".."
    assert target_component != "."


def test_create_run_tree_rejects_target_starting_with_dot(tmp_path: Path) -> None:
    """Target sanitizado que comeca com '.' (mascara hidden dir) e rejeitado
    com ValueError — defensiva contra dirs ocultos no .planning/qa/."""
    hidden_scope = Scope(type="task", target=".hidden", paths=())
    with pytest.raises(ValueError, match="scope.target inválido"):
        create_run_tree(hidden_scope, project_root=tmp_path)


def test_create_run_tree_rejects_empty_target_after_sanitize(tmp_path: Path) -> None:
    """Target inteiramente non-alphanumeric (ex.: '///') vira string vazia
    apos sanitize com whitelist — rejeitado com ValueError."""
    # '///' nao tem nada na whitelist [A-Za-z0-9._-]: vira '___' (cada / -> _).
    # Pra forcar empty string apos sanitize, target precisa ser vazio direto;
    # mas Scope dataclass aceita "" como target — testamos.
    empty_scope = Scope(type="task", target="", paths=())
    with pytest.raises(ValueError, match="scope.target inválido"):
        create_run_tree(empty_scope, project_root=tmp_path)
