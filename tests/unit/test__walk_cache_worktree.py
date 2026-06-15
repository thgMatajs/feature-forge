"""Regression test: _SKIP_DIRS deve filtrar TOP-LEVEL no project_root,
não em qualquer position da path absoluta. Bug pré-W7-cluster-fix.

Quando project_root vive em `.../.claude/worktrees/<branch>/...`, o check
ingênuo `any(part in _SKIP_DIRS for part in path.parts)` casava `.claude`
no parent absoluto e filtrava TODOS os descendentes (incluindo
`tests/fixtures/`). Fix: comparar contra `path.relative_to(project_root).parts`
em vez de `path.parts`.

Cobre duas direções:
  1. Worktree-style path (parent `.claude/`) NÃO bloqueia walk
  2. Top-level `.claude/` em project_root CONTINUA filtrado (não regredir
     comportamento legítimo)
"""
from pathlib import Path

import pytest

from engine.inventory._walk_cache import invalidate_cache, walk_project


@pytest.fixture(autouse=True)
def _clear_walk_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def test_walk_project_finds_files_in_worktree_path(tmp_path: Path) -> None:
    """Quando tmp_path simula um worktree path (parent contém '.claude'),
    o walk ainda deve encontrar arquivos descendentes do project_root."""
    # Simula structure: tmp_path/.claude/worktrees/det-w1/PROJECT/...
    worktree_parent = tmp_path / ".claude" / "worktrees"
    worktree_parent.mkdir(parents=True)
    project = worktree_parent / "det-w1"
    project.mkdir()
    (project / "build.gradle.kts").write_text("// gradle config\n", encoding="utf-8")
    (project / "settings.gradle.kts").write_text("// settings\n", encoding="utf-8")

    found = walk_project(str(project), (".kts",))
    assert len(found) == 2, (
        f"Esperado 2 arquivos .kts; got {len(found)}. "
        f"Bug _SKIP_DIRS regrediu — paths sob .claude/worktrees/ ainda filtradas. "
        f"Found: {found}"
    )


def test_walk_project_still_skips_top_level_claude(tmp_path: Path) -> None:
    """Top-level `.claude/` em project_root deve continuar sendo filtrado
    (caso legítimo do _SKIP_DIRS — não regredir esse comportamento)."""
    project = tmp_path / "PROJECT"
    project.mkdir()
    (project / "src.kt").write_text("// canonical\n", encoding="utf-8")
    claude_dir = project / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.kt").write_text("// should be skipped\n", encoding="utf-8")

    found = walk_project(str(project), (".kt",))
    assert len(found) == 1
    assert found[0].name == "src.kt"
    # Settings sob .claude/ NÃO deve aparecer
    assert not any(".claude" in p.parts for p in found)
