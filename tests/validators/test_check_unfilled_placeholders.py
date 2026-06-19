"""PLACEHOLDER-VERIFY (W-DEBT) — validator de `{{...}}` crus em artefatos de feature.

Um template não-preenchido passando como 'verificado' é detection-failure. O
validator escaneia os artefatos DENTRO do dir da feature (.md/.yaml/.yml/.json)
procurando tokens `{{token}}` não-substituídos.

C-43-B (PR22-R-001): o scan varre o FILESYSTEM do dir da feature
(`f_root.rglob`), não os arquivos staged — sibling validators rodam pré-staging,
então depender de git-staged deixava o gate inerte. Estes testes escrevem os
artefatos no disco SEM `git add` pra provar a detecção pré-staging.
"""

from __future__ import annotations

from pathlib import Path

from engine.utils.paths import feature_path
from validators.check_unfilled_placeholders import validate


def _write_feature_artifact(
    project_root: Path, slug: str, filename: str, content: str
) -> Path:
    """Escreve um artefato no dir resolvido da feature (product), sem git add."""
    f_root = feature_path(project_root, slug, subtype="product")
    f_root.mkdir(parents=True, exist_ok=True)
    p = f_root / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_passes_when_no_placeholders(tmp_path: Path) -> None:
    _write_feature_artifact(tmp_path, "demo", "prd.md", "# PRD\nTudo preenchido.\n")
    res = validate(tmp_path, scope="feature", id="demo")
    assert res["status"] == "pass"


def test_fails_on_raw_placeholder(tmp_path: Path) -> None:
    _write_feature_artifact(
        tmp_path, "demo", "prd.md", "# PRD\nObjetivo: {{objective}}\n"
    )
    res = validate(tmp_path, scope="feature", id="demo")
    assert res["status"] == "fail"
    assert "objective" in str(res)


def test_fails_on_unstaged_placeholder(tmp_path: Path) -> None:
    """C-43-B: artefato UNSTAGED com {{token}} cru hard-faila (filesystem scan)."""
    _write_feature_artifact(
        tmp_path, "demo", "bdd.json", '{"goal": "{{goal}}"}\n'
    )
    # Nenhum git init / git add — o scan é puro filesystem.
    res = validate(tmp_path, scope="feature", id="demo")
    assert res["status"] == "fail"
    assert "goal" in str(res)


def test_ignores_non_feature_files(tmp_path: Path) -> None:
    """Arquivos fora do dir da feature não contam (src/Foo.kt no root)."""
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "Foo.kt").write_text('val x = "{{not_a_feature_artifact}}"', encoding="utf-8")
    res = validate(tmp_path, scope="feature", id="demo")
    assert res["status"] == "pass"


def test_passes_when_no_slug(tmp_path: Path) -> None:
    """Sem slug de feature resolvível (id é TASK-NNNN) → scan pulado (pass)."""
    _write_feature_artifact(tmp_path, "demo", "prd.md", "# PRD\n{{objective}}\n")
    res = validate(tmp_path, scope="inferred", id="TASK-0001")
    assert res["status"] == "pass"


def test_ignores_non_artifact_suffix_inside_feature(tmp_path: Path) -> None:
    """Arquivo não-artefato (.py) dentro do dir da feature não é escaneado."""
    _write_feature_artifact(tmp_path, "demo", "helper.py", 'x = "{{still_raw}}"\n')
    res = validate(tmp_path, scope="feature", id="demo")
    assert res["status"] == "pass"


def test_feature_slug_with_task_prefix_not_misclassified(tmp_path: Path) -> None:
    """C-45: uma feature slugada `task-foo` (kebab) NÃO vira task id.

    O id `task-onboarding` em scope inferred deve ser tratado como slug — o
    regex estrito `^TASK-\\d+$` só casa `TASK-1234`, não `task-onboarding`.
    """
    _write_feature_artifact(
        tmp_path, "task-onboarding", "prd.md", "# PRD\n{{objective}}\n"
    )
    res = validate(tmp_path, scope="inferred", id="task-onboarding")
    assert res["status"] == "fail"


def test_escaped_triple_brace_is_ignored(tmp_path: Path) -> None:
    """C-52: `{{{token}}}` (triple-brace literal) não dispara o gate."""
    _write_feature_artifact(
        tmp_path, "demo", "prd.md", "# PRD\nExemplo de sintaxe: {{{token}}}\n"
    )
    res = validate(tmp_path, scope="feature", id="demo")
    assert res["status"] == "pass"


def test_escape_marker_comment_ignores_line(tmp_path: Path) -> None:
    """C-52: linha precedida por `<!-- placeholder-ok -->` é pulada."""
    _write_feature_artifact(
        tmp_path,
        "demo",
        "prd.md",
        "# PRD\n<!-- placeholder-ok -->\nMostrar `{{token}}` literal aqui.\n",
    )
    res = validate(tmp_path, scope="feature", id="demo")
    assert res["status"] == "pass"
