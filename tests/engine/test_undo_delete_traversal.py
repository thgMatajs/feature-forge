"""H-06 regression: undo delete-feature must refuse paths outside project."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.undo import _delete_feature_artifacts_guard


def test_delete_guard_rejects_path_outside_project(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    escaped = tmp_path / "outside"
    escaped.mkdir()

    with pytest.raises(ValueError, match="outside project"):
        _delete_feature_artifacts_guard(project_root, escaped)


def test_delete_guard_accepts_path_inside_project(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    inside = project_root / "docs" / "feat" / "x"
    inside.mkdir(parents=True)

    # Should not raise.
    _delete_feature_artifacts_guard(project_root, inside)


# A-013 (master review PR #15): cobertura extra pro vetor de A-001 +
# symlink-out + slug literal `../../..`.


def test_delete_guard_rejects_project_root_itself(tmp_path: Path) -> None:
    """A-001: `target == project_root` deve ser rejeitado.

    `Path.relative_to` retorna `Path('.')` na equality (sem ValueError); sem o
    check explícito de igualdade, um slug malicioso `../../..` resolveria pra
    raiz e `shutil.rmtree` apagaria o projeto inteiro após os 2 confirms.
    """
    project_root = tmp_path / "proj"
    project_root.mkdir()

    with pytest.raises(ValueError, match="project root"):
        _delete_feature_artifacts_guard(project_root, project_root)


def test_delete_guard_rejects_symlink_escaping_project(tmp_path: Path) -> None:
    """A-013: symlink dentro do project apontando pra fora deve ser rejeitado.

    `target.resolve()` segue o symlink; o `relative_to` check então compara o
    alvo real (fora do projeto) com `project_root`, e o guard rejeita.
    """
    project_root = tmp_path / "proj"
    project_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = project_root / "feature-link"
    link.symlink_to(outside)

    with pytest.raises(ValueError, match="outside project"):
        _delete_feature_artifacts_guard(project_root, link)


def test_delete_guard_rejects_literal_dotdot_slug(tmp_path: Path) -> None:
    """A-013: slug literal `../../..` resolvido contra project_root → raiz.

    Reproduz o vetor de A-001: um `feature_dir(project_root, '../../..')`
    constrói path que resolve pra fora; guard rejeita.
    """
    project_root = tmp_path / "proj"
    project_root.mkdir()
    malicious = project_root / "features" / "../../.."

    with pytest.raises(ValueError):
        _delete_feature_artifacts_guard(project_root, malicious)
