"""Unit tests — engine.utils.paths.

Validates project-root discovery, canonical paths under `.claude/`, and the
ensure_dir idempotency contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.utils import paths


def test_forge_home_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGE_HOME", str(tmp_path))
    assert paths.forge_home() == tmp_path.resolve()


def test_forge_home_fallback(monkeypatch):
    monkeypatch.delenv("FORGE_HOME", raising=False)
    home = paths.forge_home()
    assert home.is_dir()
    # Fallback must still resolve to a real directory containing the engine package.
    assert (home / "engine").is_dir()


def test_find_project_root_walks_upward(tmp_path):
    (tmp_path / "sub" / "nested").mkdir(parents=True)
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "workflow-config.yaml").write_text("schema-version: 1\n", encoding="utf-8")
    found = paths.find_project_root(tmp_path / "sub" / "nested")
    assert found == tmp_path.resolve()


def test_find_project_root_finds_forge_config_marker(tmp_path):
    """v1.3+ marker: só existe `.claude/forge/forge-config.yaml` (o que
    `forge init` cria), sem o marker legacy. Antes do fix, find_project_root
    procurava só o legacy e levantava ProjectRootNotFoundError — quebrando
    o ciclo init→uso pra projetos greenfield v1.3+.
    """
    forge_dir = tmp_path / ".claude" / "forge"
    forge_dir.mkdir(parents=True)
    (forge_dir / "forge-config.yaml").write_text(
        "schema-version: 1\n", encoding="utf-8"
    )
    found = paths.find_project_root(tmp_path)
    assert found == tmp_path.resolve()


def test_find_project_root_finds_legacy_marker(tmp_path):
    """Compat v1.2: só existe `.claude/workflow-config.yaml` (marker legacy).
    O fix é aditivo — o caminho legacy continua resolvendo.
    """
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "workflow-config.yaml").write_text(
        "schema-version: 1\n", encoding="utf-8"
    )
    found = paths.find_project_root(tmp_path)
    assert found == tmp_path.resolve()


def test_find_project_root_walks_upward_with_forge_config(tmp_path):
    """Walk-up: a raiz com o marker v1.3+ está N níveis acima do `start`."""
    (tmp_path / "sub" / "deep").mkdir(parents=True)
    forge_dir = tmp_path / ".claude" / "forge"
    forge_dir.mkdir(parents=True)
    (forge_dir / "forge-config.yaml").write_text("{}\n", encoding="utf-8")
    found = paths.find_project_root(tmp_path / "sub" / "deep")
    assert found == tmp_path.resolve()


def test_find_project_root_raises_when_missing(tmp_path):
    with pytest.raises(paths.ProjectRootNotFoundError):
        paths.find_project_root(tmp_path)


def test_try_find_project_root_returns_none(tmp_path):
    assert paths.try_find_project_root(tmp_path) is None


def test_active_config_path_prefers_forge_config_when_present(tmp_path):
    """Precedência primária: se `.claude/forge/forge-config.yaml` existe, o
    resolver retorna ele — é o destino canônico v1.3+ que `forge init` grava.
    """
    forge_dir = tmp_path / ".claude" / "forge"
    forge_dir.mkdir(parents=True)
    (forge_dir / "forge-config.yaml").write_text("schema-version: 1\n", encoding="utf-8")
    assert paths.active_config_path(tmp_path) == paths.forge_config_path(tmp_path)


def test_active_config_path_falls_back_to_legacy_when_only_legacy(tmp_path):
    """Compat v1.2: se só o legacy `.claude/workflow-config.yaml` existe, o
    resolver cai pra ele — projetos antigos continuam resolvendo a config.
    """
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "workflow-config.yaml").write_text("schema-version: 1\n", encoding="utf-8")
    assert paths.active_config_path(tmp_path) == paths.workflow_config_path(tmp_path)


def test_active_config_path_returns_primary_when_neither_exists(tmp_path):
    """Projeto novo sem nenhum dos dois: retorna o PRIMÁRIO (forge-config),
    que é o destino canônico de escrita — nunca o legado.
    """
    assert paths.active_config_path(tmp_path) == paths.forge_config_path(tmp_path)


def test_active_config_path_prefers_forge_when_both_exist(tmp_path):
    """Quando os dois coexistem (projeto migrado parcialmente), o primário
    vence — sem split de config.
    """
    forge_dir = tmp_path / ".claude" / "forge"
    forge_dir.mkdir(parents=True)
    (forge_dir / "forge-config.yaml").write_text("schema-version: 1\n", encoding="utf-8")
    (tmp_path / ".claude" / "workflow-config.yaml").write_text(
        "schema-version: 1\n", encoding="utf-8"
    )
    assert paths.active_config_path(tmp_path) == paths.forge_config_path(tmp_path)


def test_canonical_paths(tmp_path):
    assert paths.workflow_config_path(tmp_path) == tmp_path / ".claude" / "workflow-config.yaml"
    assert paths.claude_dir(tmp_path) == tmp_path / ".claude"
    assert paths.cards_dir(tmp_path) == tmp_path / ".claude" / "cards"
    assert paths.inventory_dir(tmp_path) == tmp_path / ".claude" / "inventory"
    assert paths.memory_dir(tmp_path) == tmp_path / ".claude" / "memory"
    assert paths.memory_l1_path(tmp_path, "slug-x") == tmp_path / ".claude" / "memory" / "L1" / "slug-x"
    assert paths.memory_l2_path(tmp_path) == tmp_path / ".claude" / "memory" / "L2-project.yaml"
    assert paths.graph_db_path(tmp_path) == tmp_path / ".claude" / "graph.db"
    assert paths.hooks_dir(tmp_path) == tmp_path / ".claude" / "hooks"


def test_feature_dir(tmp_path):
    assert paths.feature_dir(tmp_path, "auth") == tmp_path / "docs" / "feature-implementation-workflow" / "features" / "auth"


def test_ensure_dir_is_idempotent(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    assert not target.exists()
    paths.ensure_dir(target)
    assert target.is_dir()
    # Second call must not raise.
    paths.ensure_dir(target)
    assert target.is_dir()


def test_cards_canonical_dir_uses_forge_home(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGE_HOME", str(tmp_path))
    assert paths.cards_canonical_dir() == tmp_path.resolve() / "cards"
