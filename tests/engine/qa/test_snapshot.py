"""Tests for ``engine.qa.ingest.snapshot_artefacts`` (Phase 0 snapshot).

CONF-002 (Wave 2 SDD gap closure): SDD §5.0 exige snapshot dos
artefatos resolvidos em ``<run>/snapshot/`` (hardlinks ou copy). Antes
``snapshot_dir`` ficava vazio — agora ``run_qa`` invoca
``snapshot_artefacts`` em Phase 0.

Comportamento testado:

- Hardlink preferido; copy2 como fallback quando ``os.link`` falha.
- Estrutura relativa a ``project_root`` preservada dentro do snapshot.
- Paths inexistentes pulados silenciosamente.
- Caso patologico (path absoluto fora do root) achatado pro nome.
"""

from __future__ import annotations

import os
from pathlib import Path

from engine.qa.ingest import create_run_tree, snapshot_artefacts
from engine.qa.scope import Scope


def _setup_proj_with_files(tmp_path: Path) -> Path:
    """Cria layout minimo (.git + alguns arquivos) e devolve project_root."""
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / "docs").mkdir()
    (proj / "docs" / "spec.yaml").write_text("foo: bar\n", encoding="utf-8")
    (proj / "validators").mkdir()
    (proj / "validators" / "v.py").write_text(
        "print('hi')\n", encoding="utf-8"
    )
    return proj


def test_phase0_snapshot_copies_resolved_artefacts(tmp_path: Path) -> None:
    """Helper copia 2 arquivos preservando estrutura relativa."""
    proj = _setup_proj_with_files(tmp_path)
    scope = Scope(
        type="feature",
        target="snap-feature",
        paths=(proj / "docs" / "spec.yaml", proj / "validators" / "v.py"),
    )
    tree = create_run_tree(scope, project_root=proj)

    copied = snapshot_artefacts(scope, tree.snapshot_dir, project_root=proj)

    assert len(copied) == 2
    # Estrutura relativa preservada
    spec_dest = tree.snapshot_dir / "docs" / "spec.yaml"
    val_dest = tree.snapshot_dir / "validators" / "v.py"
    assert spec_dest.is_file()
    assert val_dest.is_file()
    # Conteudo bate
    assert spec_dest.read_text(encoding="utf-8") == "foo: bar\n"
    assert val_dest.read_text(encoding="utf-8") == "print('hi')\n"


def test_snapshot_skip_missing_src_silently(tmp_path: Path) -> None:
    """Path inexistente em scope.paths nao raise — apenas pulado."""
    proj = _setup_proj_with_files(tmp_path)
    scope = Scope(
        type="feature",
        target="snap-missing",
        paths=(
            proj / "docs" / "spec.yaml",
            proj / "does" / "not" / "exist.yaml",
        ),
    )
    tree = create_run_tree(scope, project_root=proj)

    copied = snapshot_artefacts(scope, tree.snapshot_dir, project_root=proj)

    # So 1 path existia
    assert len(copied) == 1
    assert (tree.snapshot_dir / "docs" / "spec.yaml").is_file()


def test_snapshot_fallback_to_copy_when_hardlink_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """``os.link`` raise OSError -> fallback shutil.copy2; dest existe."""
    proj = _setup_proj_with_files(tmp_path)
    scope = Scope(
        type="feature",
        target="snap-fallback",
        paths=(proj / "docs" / "spec.yaml",),
    )
    tree = create_run_tree(scope, project_root=proj)

    # Forca os.link a falhar — simula cross-device link (EXDEV)
    def _broken_link(_src, _dst):
        raise OSError(18, "Invalid cross-device link (simulated)")

    monkeypatch.setattr("engine.qa.ingest.os.link", _broken_link)

    copied = snapshot_artefacts(scope, tree.snapshot_dir, project_root=proj)

    assert len(copied) == 1
    dest = tree.snapshot_dir / "docs" / "spec.yaml"
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == "foo: bar\n"
    # Em fallback copy2, dest e arquivo NOVO (inode diferente do src)
    src_stat = (proj / "docs" / "spec.yaml").stat()
    dest_stat = dest.stat()
    assert src_stat.st_ino != dest_stat.st_ino, (
        "fallback nao usou copy — ainda hardlinkou"
    )


def test_snapshot_empty_paths_returns_empty(tmp_path: Path) -> None:
    """scope.paths vazio -> lista vazia, sem erro."""
    proj = _setup_proj_with_files(tmp_path)
    scope = Scope(type="feature", target="empty", paths=())
    tree = create_run_tree(scope, project_root=proj)
    copied = snapshot_artefacts(scope, tree.snapshot_dir, project_root=proj)
    assert copied == []


def test_snapshot_handles_path_outside_project_root(tmp_path: Path) -> None:
    """Path absoluto fora do project_root vira flat (snapshot_dir/<name>)."""
    proj = _setup_proj_with_files(tmp_path)
    # Cria arquivo fora do project_root
    outside = tmp_path / "external" / "outside.yaml"
    outside.parent.mkdir()
    outside.write_text("alien: true\n", encoding="utf-8")

    scope = Scope(type="feature", target="outside", paths=(outside,))
    tree = create_run_tree(scope, project_root=proj)

    copied = snapshot_artefacts(scope, tree.snapshot_dir, project_root=proj)

    assert len(copied) == 1
    flat_dest = tree.snapshot_dir / "outside.yaml"
    assert flat_dest.is_file()
