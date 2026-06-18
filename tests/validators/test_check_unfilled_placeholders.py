"""PLACEHOLDER-VERIFY (W-DEBT) — validator de `{{...}}` crus em artefatos de feature.

Um template não-preenchido passando como 'verificado' é detection-failure. O
validator escaneia os artefatos staged DENTRO do dir da feature (.md/.yaml/.yml/
.json) procurando tokens `{{token}}` não-substituídos. Arquivos-fonte fora do
dir da feature (ex.: src/Foo.kt) NÃO contam — só os artefatos preenchidos.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine.utils.paths import feature_path
from validators.check_unfilled_placeholders import validate


@pytest.fixture
def tmp_git_project(tmp_path: Path) -> Path:
    """Repo git mínimo pra exercitar `git_staged_files` de verdade."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _stage(project_root: Path, rel: str, content: str) -> None:
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=project_root, check=True)


def _feature_rel(project_root: Path, slug: str, filename: str) -> str:
    """Path relativo de um artefato dentro do dir resolvido da feature (product)."""
    f_root = feature_path(project_root, slug, subtype="product")
    return str((f_root / filename).relative_to(project_root))


def test_passes_when_no_placeholders(tmp_git_project: Path) -> None:
    rel = _feature_rel(tmp_git_project, "demo", "prd.md")
    _stage(tmp_git_project, rel, "# PRD\nTudo preenchido.\n")
    res = validate(tmp_git_project, scope="feature", id="demo")
    assert res["status"] == "pass"


def test_fails_on_raw_placeholder(tmp_git_project: Path) -> None:
    rel = _feature_rel(tmp_git_project, "demo", "prd.md")
    _stage(tmp_git_project, rel, "# PRD\nObjetivo: {{objective}}\n")
    res = validate(tmp_git_project, scope="feature", id="demo")
    assert res["status"] == "fail"
    assert "objective" in str(res)


def test_ignores_non_feature_files(tmp_git_project: Path) -> None:
    _stage(tmp_git_project, "src/Foo.kt", 'val x = "{{not_a_feature_artifact}}"')
    res = validate(tmp_git_project, scope="feature", id="demo")
    assert res["status"] == "pass"


def test_passes_when_no_slug(tmp_git_project: Path) -> None:
    """Sem slug de feature resolvível → scan pulado (pass)."""
    rel = _feature_rel(tmp_git_project, "demo", "prd.md")
    _stage(tmp_git_project, rel, "# PRD\n{{objective}}\n")
    res = validate(tmp_git_project, scope="inferred", id="TASK-0001")
    assert res["status"] == "pass"


def test_ignores_non_artifact_suffix_inside_feature(tmp_git_project: Path) -> None:
    """Arquivo não-artefato (.py) dentro do dir da feature não é escaneado."""
    rel = _feature_rel(tmp_git_project, "demo", "helper.py")
    _stage(tmp_git_project, rel, 'x = "{{still_raw}}"\n')
    res = validate(tmp_git_project, scope="feature", id="demo")
    assert res["status"] == "pass"


def test_reuses_shared_diff_helper() -> None:
    """Reuse-first: git_staged_files deve ser o objeto compartilhado de _diff."""
    import importlib

    mod = importlib.import_module("check_unfilled_placeholders")
    from _diff import git_staged_files as shared

    assert mod.git_staged_files is shared
